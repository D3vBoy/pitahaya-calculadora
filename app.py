from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io
from supabase import create_client, Client
from dotenv import load_dotenv
import logging

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pitahaya-secret-key-2026')

# ============================================
# CONFIGURACIÓN SUPABASE
# ============================================
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("SUPABASE_URL y SUPABASE_KEY deben estar definidos en .env")
    raise ValueError("Credenciales de Supabase no configuradas")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
logger.info("✅ Supabase client initialized successfully")

# ============================================
# FACTORES DE CÁLCULO
# ============================================
RENTA_ANUAL = 0.122  # 12.2%
PLUSVALIA_FACTOR = 0.9  # 90%
CETES_TASA = 0.0737  # 7.37%
BOLSA_TASA = 0.105  # 10.5%
SOFIPO_TASA = 0.13  # 13%
TOPE_PROSOFIPO = 218304  # $218,304
AÑOS = 20

# ============================================
# FUNCIONES SUPABASE
# ============================================
def guardar_lead(nombre, telefono, email, ip):
    """Guarda un lead en Supabase"""
    try:
        data = {
            'nombre': nombre,
            'telefono': telefono,
            'email': email,
            'ip': ip,
            'created_at': datetime.now().isoformat()
        }
        
        response = supabase.table('leads').insert(data).execute()
        
        if hasattr(response, 'data') and response.data:
            logger.info(f"✅ Lead guardado: {nombre} - {email}")
            return True
        else:
            logger.error(f"❌ No se pudo verificar la inserción")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error guardando lead: {str(e)}")
        return False

# ============================================
# RUTAS PRINCIPALES
# ============================================
@app.route('/')
def index():
    """Página de registro obligatorio"""
    return render_template('registro.html')

@app.route('/registrar', methods=['POST'])
def registrar():
    """Procesa el formulario de registro"""
    nombre = request.form.get('nombre', '').strip()
    telefono = request.form.get('telefono', '').strip()
    email = request.form.get('email', '').strip()
    ip = request.remote_addr
    
    # Validaciones
    errores = []
    if not nombre or len(nombre.split()) < 2:
        errores.append('Ingresa nombre y apellido válidos')
    if not telefono or not telefono.replace(' ', '').isdigit() or len(telefono.replace(' ', '')) < 10:
        errores.append('Ingresa un teléfono válido de 10 dígitos')
    if not email or '@' not in email or '.' not in email:
        errores.append('Ingresa un email válido')
    
    if errores:
        return render_template('registro.html', errores=errores, datos={
            'nombre': nombre,
            'telefono': telefono,
            'email': email
        })
    
    # Guardar en Supabase
    if guardar_lead(nombre, telefono, email, ip):
        session['registrado'] = True
        session['nombre_cliente'] = nombre
        session['telefono_cliente'] = telefono
        session['email_cliente'] = email
        return redirect(url_for('calculadora'))
    else:
        errores.append('Error al guardar tus datos. Intenta nuevamente.')
        return render_template('registro.html', errores=errores, datos={
            'nombre': nombre,
            'telefono': telefono,
            'email': email
        })

@app.route('/calculadora')
def calculadora():
    """Página de la calculadora"""
    if not session.get('registrado'):
        return redirect(url_for('index'))
    return render_template('calculadora.html', nombre=session.get('nombre_cliente'))

@app.route('/modificar-datos', methods=['GET', 'POST'])
def modificar_datos():
    """Modificar datos del cliente"""
    if not session.get('registrado'):
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        telefono = request.form.get('telefono', '').strip()
        email = request.form.get('email', '').strip()
        
        errores = []
        if not nombre or len(nombre.split()) < 2:
            errores.append('Ingresa nombre y apellido válidos')
        if not telefono or not telefono.replace(' ', '').isdigit() or len(telefono.replace(' ', '')) < 10:
            errores.append('Ingresa un teléfono válido de 10 dígitos')
        if not email or '@' not in email or '.' not in email:
            errores.append('Ingresa un email válido')
        
        if errores:
            return render_template('modificar_datos.html', errores=errores, datos={
                'nombre': nombre,
                'telefono': telefono,
                'email': email
            })
        
        session['nombre_cliente'] = nombre
        session['telefono_cliente'] = telefono
        session['email_cliente'] = email
        return redirect(url_for('calculadora'))
    
    return render_template('modificar_datos.html', datos={
        'nombre': session.get('nombre_cliente', ''),
        'telefono': session.get('telefono_cliente', ''),
        'email': session.get('email_cliente', '')
    })

@app.route('/calcular', methods=['POST'])
def calcular():
    """API para cálculos en tiempo real"""
    if not session.get('registrado'):
        return {'error': 'No autorizado'}, 401
    
    data = request.get_json()
    capital = float(data.get('capital', 500000))
    
    if capital < 80000 or capital > 1000000:
        return {'error': 'Capital fuera de rango'}, 400
    
    renta_anual = capital * RENTA_ANUAL
    rentas_20años = renta_anual * AÑOS
    plusvalia = capital * PLUSVALIA_FACTOR
    total_pitahaya = capital + rentas_20años + plusvalia
    
    total_cetes = capital + (capital * CETES_TASA * AÑOS)
    total_bolsa = capital + (capital * BOLSA_TASA * AÑOS)
    total_sofipo = capital + (capital * SOFIPO_TASA * AÑOS)
    monto_no_protegido = max(0, capital - TOPE_PROSOFIPO)
    
    return jsonify({
        'pitahaya': {
            'total': round(total_pitahaya, 2),
            'rentas': round(rentas_20años, 2),
            'plusvalia': round(plusvalia, 2)
        },
        'cetes': round(total_cetes, 2),
        'bolsa': round(total_bolsa, 2),
        'sofipo': round(total_sofipo, 2),
        'monto_no_protegido': round(monto_no_protegido, 2),
        'capital': capital
    })

# ============================================
# GENERACIÓN DE PDF (VERSIÓN COMPLETA RESTAURADA)
# ============================================
@app.route('/generar-pdf', methods=['POST'])
def generar_pdf():
    """Genera un PDF con los resultados de la simulación y marca de agua"""
    if not session.get('registrado'):
        return {'error': 'No autorizado'}, 401
    
    data = request.get_json()
    capital = float(data.get('capital', 500000))
    nombre = session.get('nombre_cliente', 'Cliente')
    capital = min(max(capital, 80000), 1000000)
    
    # Calcular resultados
    renta_anual = capital * RENTA_ANUAL
    rentas_20años = renta_anual * AÑOS
    plusvalia = capital * PLUSVALIA_FACTOR
    total_pitahaya = capital + rentas_20años + plusvalia
    
    total_cetes = capital + (capital * CETES_TASA * AÑOS)
    total_bolsa = capital + (capital * BOLSA_TASA * AÑOS)
    total_sofipo = capital + (capital * SOFIPO_TASA * AÑOS)
    monto_no_protegido = max(0, capital - TOPE_PROSOFIPO)
    
    # Crear PDF
    pdf_buffer = crear_pdf(
        nombre=nombre,
        capital=capital,
        total_pitahaya=total_pitahaya,
        rentas=rentas_20años,
        plusvalia=plusvalia,
        cetes=total_cetes,
        bolsa=total_bolsa,
        sofipo=total_sofipo,
        monto_no_protegido=monto_no_protegido
    )
    
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"pitahaya_simulacion_{int(capital)}.pdf",
        mimetype='application/pdf'
    )

def crear_pdf(nombre, capital, total_pitahaya, rentas, plusvalia, 
             cetes, bolsa, sofipo, monto_no_protegido):
    """Crea un PDF profesional con los resultados y marca de agua"""
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=50,
        bottomMargin=50,
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Estilos personalizados
    styles.add(ParagraphStyle(
        name='CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#ff69b4'),
        spaceAfter=20,
        alignment=1,
    ))
    
    styles.add(ParagraphStyle(
        name='Subtitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#c71585'),
        spaceAfter=10,
    ))
    
    styles.add(ParagraphStyle(
        name='Disclaimer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#666666'),
        alignment=1,
    ))
    
    # ========================================
    # 1. TÍTULO
    # ========================================
    title = Paragraph("🍈 Pitahaya Investments", styles['CustomTitle'])
    elements.append(title)
    
    subtitle = Paragraph(f"Simulación personalizada para: <b>{nombre}</b>", styles['Subtitle'])
    elements.append(subtitle)
    
    date_text = Paragraph(f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", styles['Normal'])
    elements.append(date_text)
    
    elements.append(Spacer(1, 0.3 * inch))
    
    # ========================================
    # 2. DATOS DE INVERSIÓN
    # ========================================
    inv_data = [
        ["Concepto", "Valor"],
        ["Inversión inicial", f"${capital:,.0f}"],
        ["Plazo", f"{AÑOS} años"],
        ["Tasa Pitahaya (renta)", f"{RENTA_ANUAL*100:.1f}% anual"],
        ["Plusvalía estimada", f"{PLUSVALIA_FACTOR*100:.0f}% del capital"],
    ]
    
    inv_table = Table(inv_data, colWidths=[3*inch, 2.5*inch])
    inv_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#ff69b4')),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#ffb6c1')),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 1), (1, -1), 'Helvetica'),
    ]))
    
    elements.append(inv_table)
    elements.append(Spacer(1, 0.3 * inch))
    
    # ========================================
    # 3. COMPARATIVA DE INVERSIONES
    # ========================================
    comp_title = Paragraph("Comparativa a 20 años (interés simple, SIN reinversión)", styles['Heading2'])
    elements.append(comp_title)
    elements.append(Spacer(1, 0.1 * inch))
    
    comp_data = [
        ["Instrumento", "Valor Final"],
        ["🏡 Pitahaya", f"${total_pitahaya:,.0f}"],
        ["🏦 Cetes (7.37%)", f"${cetes:,.0f}"],
        ["📈 S&P 500 (10.5%)", f"${bolsa:,.0f}"],
        ["📱 SOFIPOS (13%)", f"${sofipo:,.0f}"],
    ]
    
    comp_table = Table(comp_data, colWidths=[3*inch, 2.5*inch])
    comp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#ff69b4')),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (1, 1), colors.HexColor('#fff0f5')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#ffb6c1')),
    ]))
    
    elements.append(comp_table)
    elements.append(Spacer(1, 0.2 * inch))
    
    # ========================================
    # 4. DETALLE PITAHAYA
    # ========================================
    detalle_title = Paragraph("Desglose Pitahaya", styles['Heading2'])
    elements.append(detalle_title)
    elements.append(Spacer(1, 0.1 * inch))
    
    detalle_data = [
        ["Concepto", "Monto"],
        ["Capital inicial", f"${capital:,.0f}"],
        ["Rentas acumuladas (20 años)", f"${rentas:,.0f}"],
        ["Plusvalía del terreno", f"${plusvalia:,.0f}"],
        ["TOTAL", f"${total_pitahaya:,.0f}"],
    ]
    
    detalle_table = Table(detalle_data, colWidths=[3*inch, 2.5*inch])
    detalle_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#ff69b4')),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 4), (1, 4), colors.HexColor('#fff0f5')),
        ('FONTNAME', (0, 4), (1, 4), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#ffb6c1')),
    ]))
    
    elements.append(detalle_table)
    elements.append(Spacer(1, 0.2 * inch))
    
    # ========================================
    # 5. ADVERTENCIA SOFIPOS
    # ========================================
    if monto_no_protegido > 0:
        warning_text = f"""
        <para>
        <b>⚠️ IMPORTANTE SOBRE SOFIPOS:</b><br/>
        El seguro PROSOFIPO solo protege hasta ${TOPE_PROSOFIPO:,.0f} por persona.<br/>
        De tu inversión de ${capital:,.0f}, 
        <b><font color='red'>${monto_no_protegido:,.0f} NO están protegidos</font></b> 
        en caso de quiebra de la SOFIPO.
        </para>
        """
        warning_paragraph = Paragraph(warning_text, styles['Italic'])
        elements.append(warning_paragraph)
        elements.append(Spacer(1, 0.2 * inch))
    
    # ========================================
    # 6. DESCARGO DE RESPONSABILIDAD Y CONTACTO
    # ========================================
    disclaimer_text = f"""
    <para>
    <b>Simulación de inversión real basada en datos históricos y proyecciones internas.</b><br/>
    Los rendimientos pasados no garantizan rendimientos futuros.<br/>
    Para una proyección más acertada y personalizada, contacta a un asesor especializado:
    </para>
    """
    disclaimer_paragraph = Paragraph(disclaimer_text, styles['Disclaimer'])
    elements.append(disclaimer_paragraph)
    elements.append(Spacer(1, 0.1 * inch))
    
    whatsapp_text = f"""
    <para>
    <b><font color='#25D366'>📱 https://wa.me/5219994540539</font></b>
    </para>
    """
    whatsapp_paragraph = Paragraph(whatsapp_text, styles['Disclaimer'])
    elements.append(whatsapp_paragraph)
    
    # ========================================
    # 7. FUNCIÓN PARA MARCA DE AGUA (WATERMARK)
    # ========================================
    def add_watermark(canvas, doc):
        """Añade una marca de agua diagonal en todas las páginas"""
        canvas.saveState()
        
        # Configurar la marca de agua
        canvas.setFont('Helvetica-Bold', 45)
        canvas.setFillColor(colors.HexColor('#cccccc'))
        canvas.setFillAlpha(0.3)
        
        # Rotar 45 grados
        canvas.rotate(45)
        
        # Dibujar varias veces para cubrir toda la página
        canvas.drawString(150, -200, "PITAHAYA INVESTMENTS")
        canvas.drawString(150, -50, "PITAHAYA INVESTMENTS")
        canvas.drawString(150, 100, "PITAHAYA INVESTMENTS")
        canvas.drawString(150, 250, "PITAHAYA INVESTMENTS")
        canvas.drawString(150, 400, "PITAHAYA INVESTMENTS")
        canvas.drawString(150, 550, "PITAHAYA INVESTMENTS")
        
        canvas.restoreState()
    
    # ========================================
    # 8. CONSTRUIR EL PDF CON WATERMARK
    # ========================================
    doc.build(
        elements,
        onFirstPage=add_watermark,
        onLaterPages=add_watermark
    )
    
    buffer.seek(0)
    return buffer

# ============================================
# INICIAR APLICACIÓN
# ============================================

# Al final del archivo, ANTES del if __name__...
app = app  # Necesario para Vercel

if __name__ == '__main__':
    print("="*50)
    print("🍈 Pitahaya Investments - Calculadora")
    print("="*50)
    app.run(debug=True)