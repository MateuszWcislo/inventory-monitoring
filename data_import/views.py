import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib import messages
import csv
from .models import ImportJob
from .services import parse_uploaded_file, analyze_product_import, execute_product_import

@login_required
def import_dashboard(request):
    """Główny widok modułu importu."""
    jobs = ImportJob.objects.filter(tenant=request.user.tenant).order_by('-created_at')
    
    context = {
        'jobs': jobs,
    }
    return render(request, 'data_import/dashboard.html', context)

@login_required
def import_job_detail(request, pk):
    """Widok szczegółów zadania importu dla modala HTMX."""
    job = get_object_or_404(ImportJob, pk=pk, tenant=request.user.tenant)
    return render(request, 'data_import/partials/job_detail.html', {'job': job})

@login_required
def import_products(request):
    """Widok importu produktów z podglądem i weryfikacją."""
    tenant = request.user.tenant
    
    if request.method == 'POST':
        action = request.POST.get('action', 'analyze')
        
        if action == 'analyze':
            uploaded_file = request.FILES.get('file')
            if not uploaded_file:
                messages.error(request, "Nie wybrano pliku do importu.")
                return render(request, 'data_import/import_products.html')
                
            try:
                rows_data = parse_uploaded_file(uploaded_file)
            except Exception as e:
                messages.error(request, f"Błąd podczas odczytu pliku: {str(e)}")
                return render(request, 'data_import/import_products.html')
                
            if not rows_data:
                messages.error(request, "Plik jest pusty lub nie zawiera poprawnych wierszy z danymi.")
                return render(request, 'data_import/import_products.html')
                
            analysis = analyze_product_import(rows_data, tenant)
            
            # Serializacja danych do sesji lub ukrytego pola na potrzeby drugiego kroku (potwierdzenia)
            # Konwertujemy Decimal do str na potrzeby serializacji JSON
            serializable_rows = []
            for r in analysis['rows']:
                r_copy = dict(r)
                p_copy = dict(r['parsed'])
                if isinstance(p_copy.get('vat_rate'), Decimal):
                    p_copy['vat_rate'] = str(p_copy['vat_rate'])
                if isinstance(p_copy.get('net_price'), Decimal):
                    p_copy['net_price'] = str(p_copy['net_price'])
                if isinstance(p_copy.get('gross_price'), Decimal):
                    p_copy['gross_price'] = str(p_copy['gross_price'])
                p_copy['supplier_obj'] = None  # usuwamy obiekt modelu
                r_copy['parsed'] = p_copy
                serializable_rows.append(r_copy)

            context = {
                'step': 'preview',
                'file_name': uploaded_file.name,
                'analysis': analysis,
                'serialized_rows_json': json.dumps(serializable_rows),
            }
            return render(request, 'data_import/import_products.html', context)

        elif action == 'confirm':
            file_name = request.POST.get('file_name', 'import_produktow')
            serialized_rows_json = request.POST.get('serialized_rows_json', '[]')
            selected_rows_indices = request.POST.getlist('selected_rows')
            
            try:
                analyzed_rows = json.loads(serialized_rows_json)
                # Odtworzenie obiektów Decimal dla stawek VAT
                for r in analyzed_rows:
                    if 'parsed' in r:
                        if 'vat_rate' in r['parsed'] and r['parsed']['vat_rate'] is not None:
                            r['parsed']['vat_rate'] = Decimal(str(r['parsed']['vat_rate']))
                        if 'net_price' in r['parsed'] and r['parsed']['net_price'] is not None:
                            r['parsed']['net_price'] = Decimal(str(r['parsed']['net_price']))
                        if 'gross_price' in r['parsed'] and r['parsed']['gross_price'] is not None:
                            r['parsed']['gross_price'] = Decimal(str(r['parsed']['gross_price']))
            except Exception as e:
                messages.error(request, f"Błąd przetwarzania danych zatwierdzenia: {str(e)}")
                return redirect('import_products')

            # Jeśli użytkownik przekazał listę wybranych wierszy (odrzucił niektóre), filtrujemy analyzed_rows
            if selected_rows_indices:
                selected_set = set(str(idx) for idx in selected_rows_indices)
                analyzed_rows = [r for r in analyzed_rows if str(r.get('row_num')) in selected_set]
            else:
                messages.warning(request, "Nie zaznaczono żadnego produktu do zaimportowania.")
                return redirect('import_products')

            if not analyzed_rows:
                messages.warning(request, "Brak produktów spełniających kryteria importu.")
                return redirect('import_products')

            # Tworzenie rekordu zadania
            job = ImportJob.objects.create(
                tenant=tenant,
                user=request.user,
                file_type='PRODUCTS',
                status='PROCESSING',
                file_name=file_name,
                records_total=len(analyzed_rows),
            )

            result = execute_product_import(analyzed_rows, tenant, user=request.user, job=job)

            context = {
                'step': 'result',
                'job': job,
                'result': result,
            }
            messages.success(request, f"Import zakończony! Dodano: {result['imported_count']}, zaktualizowano: {result['updated_count']}.")
            return render(request, 'data_import/import_products.html', context)

    return render(request, 'data_import/import_products.html', {'step': 'upload'})

@login_required
def download_product_template_csv(request):
    """Generuje szablon CSV dla produktów."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="szablon_produkty.csv"'
    
    # Dodanie BOM dla Excela, żeby poprawnie czytał polskie znaki w CSV
    response.write(u'\ufeff'.encode('utf8'))
    
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Nazwa', 'Opis', 'VAT %', 'Próg alarmowy', 'Stan docelowy', 'Cena netto', 'Cena brutto', 'Stan partii', 'SKU u dostawcy', 'Nazwa dostawcy'])
    
    # Przykładowy wiersz
    writer.writerow(['Przykładowy Produkt', 'Opis produktu', '23', '10', '20', '100.00', '123.00', '15', 'SKU-001', 'Nazwa Dostawcy'])
    
    return response

@login_required
def download_product_template_excel(request):
    """Generuje szablon Excel (.xlsx) dla produktów.
    Używamy openpyxl, a w razie problemów wysyłamy format HTML-Spreadsheet.
    """
    headers = ['Nazwa', 'Opis', 'VAT %', 'Próg alarmowy', 'Stan docelowy', 'Cena netto', 'Cena brutto', 'Stan partii', 'SKU u dostawcy', 'Nazwa dostawcy']
    sample_row = ['Przykładowy Produkt', 'Opis produktu', 23, 10, 20, 100.00, 123.00, 15, 'SKU-001', 'Nazwa Dostawcy']
    try:
        import openpyxl
        import io
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Produkty"
        
        ws.append(headers)
        ws.append(sample_row)
        
        output = io.BytesIO()
        wb.save(output)
        
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="szablon_produkty.xlsx"'
        return response
        
    except (ImportError, ModuleNotFoundError, Exception):
        # Fallback do formatu HTML, który Excel otwiera idealnie z podziałem na komórki
        content = """
        <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40">
        <head><meta http-equiv="content-type" content="application/vnd.ms-excel; charset=UTF-8"></head>
        <body>
            <table>
                <tr>
                    <th>Nazwa</th><th>Opis</th><th>VAT %</th><th>Próg alarmowy</th><th>Stan docelowy</th><th>Cena netto</th><th>Cena brutto</th><th>Stan partii</th><th>SKU u dostawcy</th><th>Nazwa dostawcy</th>
                </tr>
                <tr>
                    <td>Przykładowy Produkt</td><td>Opis produktu</td><td>23</td><td>10</td><td>20</td><td>100.00</td><td>123.00</td><td>15</td><td>SKU-001</td><td>Nazwa Dostawcy</td>
                </tr>
            </table>
        </body>
        </html>
        """
        response = HttpResponse(content, content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = 'attachment; filename="szablon_produkty.xls"'
        return response
