from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
import csv
from .models import ImportJob

@login_required
def import_dashboard(request):
    """Główny widok modułu importu."""
    jobs = ImportJob.objects.filter(tenant=request.user.tenant).order_by('-created_at')
    
    context = {
        'jobs': jobs,
    }
    return render(request, 'data_import/dashboard.html', context)

@login_required
def import_products(request):
    """Widok importu produktów."""
    # Tu w przyszłości logika obsługi POST z plikiem
    return render(request, 'data_import/import_products.html')

@login_required
def download_product_template_csv(request):
    """Generuje szablon CSV dla produktów."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="szablon_produkty.csv"'
    
    # Dodanie BOM dla Excela, żeby poprawnie czytał polskie znaki w CSV
    response.write(u'\ufeff'.encode('utf8'))
    
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Nazwa', 'Opis', 'VAT %', 'Próg alarmowy', 'Stan docelowy', 'SKU u dostawcy', 'Nazwa dostawcy'])
    
    # Przykładowy wiersz
    writer.writerow(['Przykładowy Produkt', 'Opis produktu', '23', '10', '20', 'SKU-001', 'Nazwa Dostawcy'])
    
    return response

@login_required
def download_product_template_excel(request):
    """Generuje szablon Excel (.xlsx) dla produktów.
    Używamy pandas, jeśli dostępny, w przeciwnym razie wysyłamy poprawnie sformatowany CSV udający Excel.
    """
    try:
        import pandas as pd
        import io
        
        df = pd.DataFrame(columns=['Nazwa', 'Opis', 'VAT %', 'Próg alarmowy', 'Stan docelowy', 'SKU u dostawcy', 'Nazwa dostawcy'])
        # Przykładowy wiersz
        df.loc[0] = ['Przykładowy Produkt', 'Opis produktu', '23', '10', '20', 'SKU-001', 'Nazwa Dostawcy']
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Produkty')
        
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="szablon_produkty.xlsx"'
        return response
        
    except (ImportError, ModuleNotFoundError):
        # Fallback do formatu HTML, który Excel otwiera idealnie z podziałem na komórki
        content = """
        <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40">
        <head><meta http-equiv="content-type" content="application/vnd.ms-excel; charset=UTF-8"></head>
        <body>
            <table>
                <tr>
                    <th>Nazwa</th><th>Opis</th><th>VAT %</th><th>Próg alarmowy</th><th>Stan docelowy</th><th>SKU u dostawcy</th><th>Nazwa dostawcy</th>
                </tr>
                <tr>
                    <td>Przykładowy Produkt</td><td>Opis produktu</td><td>23</td><td>10</td><td>20</td><td>SKU-001</td><td>Nazwa Dostawcy</td>
                </tr>
            </table>
        </body>
        </html>
        """
        response = HttpResponse(content, content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = 'attachment; filename="szablon_produkty.xls"'
        return response
