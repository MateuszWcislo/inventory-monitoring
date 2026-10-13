import csv
import io
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.db import transaction
import openpyxl

from inventory.models import Product, ProductBatch, ProductSupplier
from suppliers.models import Supplier
from .models import ImportJob

def parse_uploaded_file(file):
    """
    Parsuje przesłany plik (CSV, XLSX, XLS/HTML) i zwraca listę słowników z wierszami.
    """
    file_name = file.name.lower()
    raw_content = file.read()
    
    if file_name.endswith('.xlsx'):
        return _parse_xlsx(raw_content)
    elif file_name.endswith('.csv'):
        return _parse_csv(raw_content)
    elif file_name.endswith('.xls'):
        # Może to być plik HTML (generowany fallback) lub XLSX/CSV z rozszerzeniem .xls
        try:
            return _parse_xlsx(raw_content)
        except Exception:
            try:
                return _parse_html_table(raw_content)
            except Exception:
                return _parse_csv(raw_content)
    else:
        # Domyślna próba CSV
        return _parse_csv(raw_content)

def _parse_csv(raw_content):
    # Wykrywanie kodowania utf-8, utf-8-sig, cp1250, latin2
    text = None
    for encoding in ['utf-8-sig', 'utf-8', 'cp1250', 'iso-8859-2']:
        try:
            text = raw_content.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        text = raw_content.decode('utf-8', errors='ignore')

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    # Wykrywanie separatora (; , \t)
    sample = lines[0]
    delimiter = ';'
    if '\t' in sample:
        delimiter = '\t'
    elif ';' in sample:
        delimiter = ';'
    elif ',' in sample:
        delimiter = ','

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return []

    headers = [h.strip() for h in rows[0]]
    data_rows = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        row_dict = {}
        for idx, header in enumerate(headers):
            row_dict[header] = row[idx].strip() if idx < len(row) else ''
        data_rows.append(row_dict)
    return data_rows

def _parse_xlsx(raw_content):
    wb = openpyxl.load_workbook(io.BytesIO(raw_content), data_only=True)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(h).strip() if h is not None else f'Kolumna_{idx}' for idx, h in enumerate(rows[0])]
    data_rows = []
    for row in rows[1:]:
        if not any(cell is not None and str(cell).strip() for cell in row):
            continue
        row_dict = {}
        for idx, header in enumerate(headers):
            val = row[idx] if idx < len(row) else ''
            row_dict[header] = str(val).strip() if val is not None else ''
        data_rows.append(row_dict)
    return data_rows

def _parse_html_table(raw_content):
    try:
        text = raw_content.decode('utf-8')
    except UnicodeDecodeError:
        text = raw_content.decode('cp1250', errors='ignore')

    # Wyciąganie th i td za pomocą regex
    th_matches = re.findall(r'<th[^>]*>(.*?)</th>', text, re.IGNORECASE | re.DOTALL)
    headers = [re.sub(r'<[^>]+>', '', th).strip() for th in th_matches]

    tr_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', text, re.IGNORECASE | re.DOTALL)
    data_rows = []
    for tr in tr_matches:
        td_matches = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.IGNORECASE | re.DOTALL)
        if not td_matches:
            continue
        row = [re.sub(r'<[^>]+>', '', td).strip() for td in td_matches]
        row_dict = {}
        for idx, header in enumerate(headers):
            row_dict[header] = row[idx] if idx < len(row) else ''
        data_rows.append(row_dict)
    return data_rows


def normalize_product_row(row_dict):
    """
    Mapuje różne warianty nazw kolumn na standardowe klucze.
    """
    normalized = {
        'name': '',
        'description': '',
        'vat_rate': '23.00',
        'min_threshold': '5',
        'target_stock': '',
        'net_price': '',
        'gross_price': '',
        'current_stock': '',
        'supplier_sku': '',
        'supplier_name': '',
    }
    
    for key, val in row_dict.items():
        k = key.lower().strip()
        if k in ['nazwa', 'nazwa produktu', 'name', 'product name']:
            normalized['name'] = val
        elif k in ['opis', 'description', 'opis produktu']:
            normalized['description'] = val
        elif k in ['vat %', 'vat', 'stawka vat', 'vat_rate']:
            normalized['vat_rate'] = val
        elif k in ['próg alarmowy', 'prog alarmowy', 'progu alarmowy', 'limit', 'min_threshold', 'stan minimalny', 'min']:
            normalized['min_threshold'] = val
        elif k in ['stan docelowy', 'target_stock', 'target', 'optymalny']:
            normalized['target_stock'] = val
        elif k in ['cena netto', 'netto', 'net_price', 'cena_netto', 'cena net']:
            normalized['net_price'] = val
        elif k in ['cena brutto', 'brutto', 'gross_price', 'cena_brutto', 'cena brut']:
            normalized['gross_price'] = val
        elif k in ['stan partii', 'ilość', 'ilosc', 'stan', 'current_stock', 'stock', 'ilość w partii', 'ilosc partii']:
            normalized['current_stock'] = val
        elif k in ['sku u dostawcy', 'sku dostawcy', 'supplier_sku', 'sku', 'kod towaru dostawcy']:
            normalized['supplier_sku'] = val
        elif k in ['nazwa dostawcy', 'dostawca', 'supplier', 'supplier_name']:
            normalized['supplier_name'] = val

    return normalized


def analyze_product_import(rows_data, tenant):
    """
    Analizuje dane przed importem:
    - Wykrywa duplikaty w pliku na podstawie klucza: (nazwa, cena_netto, cena_brutto)
    - Waliduje i przelicza ceny netto/brutto w oparciu o stawkę VAT
    - Sprawdza istnienie partii/produktów w bazie
    - Sprawdza dostępność dostawców
    - Weryfikuje błędy formatu
    """
    analyzed_rows = []
    file_duplicates_names = set()
    seen_in_file = {}
    
    existing_products = {p.name.lower(): p for p in Product.objects.filter(tenant=tenant).prefetch_related('batches')}
    existing_suppliers = {s.name.lower(): s for s in Supplier.objects.filter(tenant=tenant)}

    for idx, raw_row in enumerate(rows_data, start=1):
        norm = normalize_product_row(raw_row)
        name = norm['name'].strip()
        
        errors = []
        warnings = []
        
        if not name:
            errors.append("Brak wymaganej nazwy produktu.")

        # Walidacja VAT
        vat_val = Decimal('23.00')
        if norm['vat_rate']:
            try:
                vat_clean = str(norm['vat_rate']).replace(',', '.').replace('%', '').strip()
                vat_val = Decimal(vat_clean)
            except (InvalidOperation, ValueError):
                errors.append(f"Nieprawidłowa stawka VAT: '{norm['vat_rate']}'.")

        # Walidacja i przeliczanie cen netto i brutto
        net_price_val = None
        gross_price_val = None
        vat_mult = 1 + (vat_val / Decimal('100'))

        if norm['net_price']:
            try:
                net_clean = str(norm['net_price']).replace(',', '.').replace('zł', '').replace('PLN', '').strip()
                net_price_val = Decimal(net_clean).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if net_price_val < 0:
                    errors.append("Cena netto nie może być ujemna.")
            except (InvalidOperation, ValueError):
                errors.append(f"Nieprawidłowa cena netto: '{norm['net_price']}'.")

        if norm['gross_price']:
            try:
                gross_clean = str(norm['gross_price']).replace(',', '.').replace('zł', '').replace('PLN', '').strip()
                gross_price_val = Decimal(gross_clean).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if gross_price_val < 0:
                    errors.append("Cena brutto nie może być ujemna.")
            except (InvalidOperation, ValueError):
                errors.append(f"Nieprawidłowa cena brutto: '{norm['gross_price']}'.")

        # Logika uzupełniania brakującej ceny oraz weryfikacji zgodności
        if net_price_val is not None and gross_price_val is None:
            gross_price_val = (net_price_val * vat_mult).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            warnings.append(f"Obliczono cenę brutto ({gross_price_val} zł) na podstawie ceny netto i stawki VAT {vat_val}%.")
        elif gross_price_val is not None and net_price_val is None:
            net_price_val = (gross_price_val / vat_mult).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            warnings.append(f"Obliczono cenę netto ({net_price_val} zł) na podstawie ceny brutto i stawki VAT {vat_val}%.")
        elif net_price_val is not None and gross_price_val is not None:
            calculated_gross = (net_price_val * vat_mult).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            # Dopuszczamy różnicę 1 grosza na zaokrągleniach, powyżej tego ostrzegamy lub korygujemy
            if abs(calculated_gross - gross_price_val) > Decimal('0.02'):
                warnings.append(f"Niezgodność cen: netto {net_price_val} zł + VAT {vat_val}% daje {calculated_gross} zł (podano brutto {gross_price_val} zł). Zastosowano cenę netto.")
                gross_price_val = calculated_gross

        # Walidacja stanu partii
        batch_stock_val = 0
        if norm['current_stock']:
            try:
                batch_stock_val = int(float(str(norm['current_stock']).replace(',', '.').strip()))
                if batch_stock_val < 0:
                    errors.append("Stan partii nie może być ujemny.")
            except (ValueError, TypeError):
                errors.append(f"Nieprawidłowa ilość w partii: '{norm['current_stock']}'.")
        
        # Klucz unikalności w pliku: (nazwa, cena_netto, cena_brutto)
        net_str = str(net_price_val) if net_price_val is not None else '0.00'
        gross_str = str(gross_price_val) if gross_price_val is not None else '0.00'
        unique_key = (name.lower(), net_str, gross_str) if name else None

        if unique_key:
            if unique_key in seen_in_file:
                dup_label = f"{name} ({net_str}/{gross_str} zł)"
                file_duplicates_names.add(dup_label)
                warnings.append(f"Zduplikowany wpis partii w pliku (poprzednio w wierszu {seen_in_file[unique_key]}).")
            else:
                seen_in_file[unique_key] = idx
                
        # Sprawdzanie czy produkt / partia już istnieje w bazie
        name_lower = name.lower()
        exists_in_db = False
        batch_exists_in_db = False
        if name and name_lower in existing_products:
            exists_in_db = True
            p_obj = existing_products[name_lower]
            if net_price_val is not None:
                # Sprawdzenie czy istnieje partia o takich cenach
                for b in p_obj.batches.all():
                    if b.net_price == net_price_val and b.gross_price == gross_price_val:
                        batch_exists_in_db = True
                        break
            if batch_exists_in_db:
                warnings.append("Partia produktu o tej cenie już istnieje w bazie (stan zostanie zaktualizowany/zwiększony).")
            else:
                warnings.append("Produkt o tej nazwie istnieje w bazie (zostanie dodana nowa partia cenowa lub zaktualizowany opis).")

        # Walidacja progu alarmowego
        min_thresh = 5
        if norm['min_threshold']:
            try:
                min_thresh = int(float(str(norm['min_threshold']).replace(',', '.').strip()))
            except (ValueError, TypeError):
                errors.append(f"Nieprawidłowy próg alarmowy: '{norm['min_threshold']}'.")

        # Walidacja stanu docelowego
        target_stk = None
        if norm['target_stock']:
            try:
                target_stk = int(float(str(norm['target_stock']).replace(',', '.').strip()))
            except (ValueError, TypeError):
                errors.append(f"Nieprawidłowy stan docelowy: '{norm['target_stock']}'.")

        # Sprawdzenie dostawcy
        supplier_obj = None
        supp_name = norm['supplier_name'].strip()
        if supp_name:
            supp_lower = supp_name.lower()
            if supp_lower in existing_suppliers:
                supplier_obj = existing_suppliers[supp_lower]
            else:
                warnings.append(f"Dostawca '{supp_name}' nie istnieje w systemie. Produkt zostanie utworzony bez powiązania z dostawcą.")

        analyzed_rows.append({
            'row_num': idx,
            'data': norm,
            'parsed': {
                'name': name,
                'description': norm['description'],
                'vat_rate': vat_val,
                'min_threshold': min_thresh,
                'target_stock': target_stk,
                'net_price': net_price_val,
                'gross_price': gross_price_val,
                'current_stock': batch_stock_val,
                'supplier_name': supp_name,
                'supplier_obj': supplier_obj,
                'supplier_sku': norm['supplier_sku'].strip(),
            },
            'exists_in_db': exists_in_db,
            'batch_exists_in_db': batch_exists_in_db,
            'errors': errors,
            'warnings': warnings,
            'is_valid': len(errors) == 0,
        })

    has_file_duplicates = len(file_duplicates_names) > 0
    total_valid = sum(1 for r in analyzed_rows if r['is_valid'])
    total_errors = sum(1 for r in analyzed_rows if not r['is_valid'])

    return {
        'rows': analyzed_rows,
        'file_duplicates_names': sorted(list(file_duplicates_names)),
        'has_file_duplicates': has_file_duplicates,
        'total_count': len(analyzed_rows),
        'total_valid': total_valid,
        'total_errors': total_errors,
    }


def execute_product_import(analyzed_rows, tenant, user=None, job=None):
    """
    Właściwy zapis przetworzonych produktów i partii towarowych (ProductBatch) do bazy.
    """
    imported_count = 0
    updated_count = 0
    failed_count = 0
    logs = []

    existing_suppliers = {s.name.lower(): s for s in Supplier.objects.filter(tenant=tenant)}

    for row in analyzed_rows:
        if not row.get('is_valid', True):
            failed_count += 1
            logs.append(f"Wiersz {row['row_num']}: Błąd walidacji - {', '.join(row['errors'])}")
            continue

        p_data = row['parsed']
        name = p_data['name']
        net_price = p_data.get('net_price')
        gross_price = p_data.get('gross_price')
        batch_stock = p_data.get('current_stock', 0)
        
        try:
            with transaction.atomic():
                product, created = Product.objects.get_or_create(
                    tenant=tenant,
                    name=name,
                    defaults={
                        'description': p_data['description'],
                        'vat_rate': p_data['vat_rate'],
                        'min_threshold': p_data['min_threshold'],
                        'target_stock': p_data['target_stock'] if p_data['target_stock'] is not None else p_data['min_threshold'],
                    }
                )

                if not created:
                    # Aktualizacja istniejącego
                    if p_data['description']:
                        product.description = p_data['description']
                    product.vat_rate = p_data['vat_rate']
                    product.min_threshold = p_data['min_threshold']
                    if p_data['target_stock'] is not None:
                        product.target_stock = p_data['target_stock']
                    product.save()
                    updated_count += 1
                    logs.append(f"Wiersz {row['row_num']}: Zaktualizowano produkt '{name}'.")
                else:
                    imported_count += 1
                    logs.append(f"Wiersz {row['row_num']}: Utworzono produkt '{name}'.")

                # Obsługa partii towaru (ProductBatch)
                # Jeśli podano ceny lub ilość w partii, tworzymy lub aktualizujemy partię
                if net_price is not None or gross_price is not None or batch_stock > 0:
                    effective_net = net_price if net_price is not None else Decimal('0.00')
                    effective_gross = gross_price if gross_price is not None else Decimal('0.00')
                    
                    batch, b_created = ProductBatch.objects.get_or_create(
                        tenant=tenant,
                        product=product,
                        net_price=effective_net,
                        gross_price=effective_gross,
                        defaults={
                            'current_stock': batch_stock
                        }
                    )
                    if not b_created:
                        if batch_stock > 0:
                            batch.current_stock = (batch.current_stock or 0) + batch_stock
                            batch.save()
                            logs.append(f"  -> Zaktualizowano partię ({effective_net} / {effective_gross} zł): dodano {batch_stock} szt. (nowy stan: {batch.current_stock}).")
                    else:
                        logs.append(f"  -> Utworzono partię ({effective_net} / {effective_gross} zł) ze stanem początkowym: {batch_stock} szt.")

                # Obsługa relacji z dostawcą
                supp_name = p_data['supplier_name']
                if supp_name:
                    supp_obj = existing_suppliers.get(supp_name.lower())
                    if supp_obj:
                        ProductSupplier.objects.update_or_create(
                            tenant=tenant,
                            product=product,
                            supplier=supp_obj,
                            defaults={
                                'supplier_sku': p_data['supplier_sku'] or None
                            }
                        )
                        logs.append(f"  -> Powiązano z dostawcą '{supp_obj.name}' (SKU: {p_data['supplier_sku'] or 'brak'}).")
                    else:
                        logs.append(f"  -> Pominięto relację z dostawcą '{supp_name}' (dostawca nie istnieje w systemie).")

        except Exception as e:
            failed_count += 1
            logs.append(f"Wiersz {row['row_num']}: Błąd zapisu produktu '{name}' - {str(e)}")

    if job:
        job.records_total = len(analyzed_rows)
        job.records_imported = imported_count + updated_count
        job.records_failed = failed_count
        job.status = 'COMPLETED' if failed_count == 0 else ('FAILED' if (imported_count + updated_count) == 0 else 'COMPLETED')
        job.error_log = "\n".join(logs)
        job.save()

    return {
        'imported_count': imported_count,
        'updated_count': updated_count,
        'failed_count': failed_count,
        'logs': logs,
    }
