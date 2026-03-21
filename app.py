from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify, make_response, send_from_directory
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
import sys
import hashlib
import uuid

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pitahaya-secret-key-2026')

# ============================================
# CONFIGURACIÓN SUPABASE
# ============================================
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

logger.info(f"SUPABASE_URL: {SUPABASE_URL}")
logger.info(f"SUPABASE_KEY: {'Configurada' if SUPABASE_KEY else 'No configurada'}")

# Inicialización diferida de Supabase (para evitar errores en Vercel)
supabase = None

def get_supabase():
    """Función para obtener el cliente de Supabase (inicialización diferida)"""
    global supabase
    if supabase is None and SUPABASE_URL and SUPABASE_KEY:
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("✅ Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"❌ Error inicializando Supabase: {str(e)}")
            supabase = None
    return supabase

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
def guardar_lead(nombre, telefono, email, ip, token=None):
    """Guarda un lead en Supabase con token opcional"""
    supabase_client = get_supabase()
    if not supabase_client:
        logger.error("Supabase no está configurado o no disponible")
        return False
    
    try:
        data = {
            'nombre': nombre,
            'telefono': telefono,
            'email': email,
            'ip': ip,
            'created_at': datetime.now().isoformat()
        }
        
        # Agregar token si se proporciona
        if token:
            data['token'] = token
        
        response = supabase_client.table('leads').insert(data).execute()
        
        if hasattr(response, 'data') and response.data:
            logger.info(f"✅ Lead guardado: {nombre} - {email}")
            return True
        else:
            logger.error(f"❌ No se pudo verificar la inserción")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error guardando lead: {str(e)}")
        return False

def buscar_lead_por_token(token):
    """Busca un lead por su token"""
    supabase_client = get_supabase()
    if not supabase_client:
        return None
    
    try:
        response = supabase_client.table('leads').select('nombre, telefono, email, token').eq('token', token).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
    except Exception as e:
        logger.error(f"Error buscando lead por token: {str(e)}")
    
    return None

def buscar_lead_por_ip(ip):
    """Busca un lead por IP (para compatibilidad con registros existentes)"""
    supabase_client = get_supabase()
    if not supabase_client:
        return None
    
    try:
        response = supabase_client.table('leads').select('nombre, telefono, email, ip').eq('ip', ip).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
    except Exception as e:
        logger.error(f"Error buscando lead por IP: {str(e)}")
    
    return None

# ============================================
# FUNCIONES PARA AUTO-LOGIN
# ============================================
def generar_token_para_ip(ip):
    """Genera un token único basado en la IP del usuario"""
    secreto = app.secret_key
    token_base = f"{ip}:{secreto}:{datetime.now().strftime('%Y%m%d')}"
    return hashlib.sha256(token_base.encode()).hexdigest()[:32]

def verificar_usuario_por_cookie():
    """Verifica si el usuario ya está registrado mediante una cookie"""
    token = request.cookies.get('pitahaya_user_token')
    if not token:
        return None
    
    # Buscar en Supabase si existe un usuario con este token
    lead = buscar_lead_por_token(token)
    if lead:
        return lead
    
    return None

def actualizar_token_lead(email, token):
    """Actualiza el lead con el token generado"""
    supabase_client = get_supabase()
    if not supabase_client:
        return False
    
    try:
        supabase_client.table('leads').update({'token': token}).eq('email', email).execute()
        logger.info(f"✅ Token actualizado para {email}")
        return True
    except Exception as e:
        logger.error(f"❌ Error actualizando token: {str(e)}")
        return False

# ============================================
# RUTA DE PRUEBA
# ============================================
@app.route('/test')
def test():
    return "✅ La app está funcionando correctamente en Vercel"

# ============================================
# FAVICON
# ============================================
@app.route('/favicon.ico')
def favicon():
    try:
        return send_from_directory(os.path.join(app.root_path, 'static'),
                                   'favicon.ico', mimetype='image/vnd.microsoft.icon')
    except:
        return "", 204

# ============================================
# RUTAS PRINCIPALES
# ============================================
@app.route('/')
def index():
    """Página de registro obligatorio con detección automática de usuario"""
    logger.info("🚀 Entrando a la ruta /")
    
    # Verificar si ya hay una cookie de usuario
    usuario = verificar_usuario_por_cookie()
    
    if usuario:
        # Usuario ya registrado, restaurar sesión y redirigir a calculadora
        session['registrado'] = True
        session['nombre_cliente'] = usuario.get('nombre')
        session['telefono_cliente'] = usuario.get('telefono')
        session['email_cliente'] = usuario.get('email')
        logger.info(f"✅ Usuario reconocido por cookie: {usuario.get('nombre')}")
        return redirect(url_for('calculadora'))
    
    # Verificar si ya hay un registro con esta IP (para migración)
    ip = request.remote_addr
    lead_existente = buscar_lead_por_ip(ip)
    
    if lead_existente:
        # Usuario existente sin token, generar token y actualizar
        token = generar_token_para_ip(ip)
        actualizar_token_lead(lead_existente.get('email'), token)
        
        # Crear respuesta con cookie
        resp = redirect(url_for('calculadora'))
        resp.set_cookie(
            'pitahaya_user_token', 
            token, 
            max_age=60*60*24*365,  # 1 año
            httponly=True,
            samesite='Lax'
        )
        
        # Restaurar sesión
        session['registrado'] = True
        session['nombre_cliente'] = lead_existente.get('nombre')
        session['telefono_cliente'] = lead_existente.get('telefono')
        session['email_cliente'] = lead_existente.get('email')
        
        logger.info(f"✅ Token generado para usuario existente: {lead_existente.get('nombre')}")
        return resp
    
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
    
    # Verificar si ya existe un lead con este email
    supabase_client = get_supabase()
    lead_existente = None
    if supabase_client:
        try:
            response = supabase_client.table('leads').select('*').eq('email', email).execute()
            if response.data and len(response.data) > 0:
                lead_existente = response.data[0]
        except:
            pass
    
    if lead_existente:
        # Usuario ya existe, actualizar token y datos
        token = generar_token_para_ip(ip)
        actualizar_token_lead(email, token)
        
        session['registrado'] = True
        session['nombre_cliente'] = lead_existente.get('nombre')
        session['telefono_cliente'] = lead_existente.get('telefono')
        session['email_cliente'] = lead_existente.get('email')
        
        resp = redirect(url_for('calculadora'))
        resp.set_cookie(
            'pitahaya_user_token', 
            token, 
            max_age=60*60*24*365,
            httponly=True,
            samesite='Lax'
        )
        return resp
    
    # Generar token único para este usuario
    token = generar_token_para_ip(ip)
    
    # Guardar en Supabase con token
    if guardar_lead(nombre, telefono, email, ip, token):
        # Guardar en sesión
        session['registrado'] = True
        session['nombre_cliente'] = nombre
        session['telefono_cliente'] = telefono
        session['email_cliente'] = email
        
        # Crear respuesta con cookie
        resp = redirect(url_for('calculadora'))
        resp.set_cookie(
            'pitahaya_user_token', 
            token, 
            max_age=60*60*24*365,  # 1 año
            httponly=True,
            samesite='Lax'
        )
        return resp
    else:
        errores.append('Error al guardar tus datos. Intenta nuevamente.')
        return render_template('registro.html', errores=errores, datos={
            'nombre': nombre,
            'telefono': telefono,
            'email': email
        })

@app.route('/check-auth')
def check_auth():
    """Verifica si el usuario ya está autenticado por cookie"""
    usuario = verificar_usuario_por_cookie()
    
    if usuario:
        # Usuario existente, actualizar sesión
        session['registrado'] = True
        session['nombre_cliente'] = usuario.get('nombre')
        session['telefono_cliente'] = usuario.get('telefono')
        session['email_cliente'] = usuario.get('email')
        return {'authenticated': True, 'nombre': usuario.get('nombre')}
    else:
        return {'authenticated': False}

@app.route('/calculadora')
def calculadora():
    """Página de la calculadora"""
    if not session.get('registrado'):
        return redirect(url_for('index'))
    try:
        return render_template('calculadora.html', nombre=session.get('nombre_cliente'))
    except Exception as e:
        logger.error(f"❌ Error cargando calculadora.html: {str(e)}")
        return f"Error cargando calculadora: {str(e)}", 500

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
    
    try:
        return render_template('modificar_datos.html', datos={
            'nombre': session.get('nombre_cliente', ''),
            'telefono': session.get('telefono_cliente', ''),
            'email': session.get('email_cliente', '')
        })
    except Exception as e:
        logger.error(f"❌ Error cargando modificar_datos.html: {str(e)}")
        return f"Error: {str(e)}", 500

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
# GENERACIÓN DE PDF
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
    
    try:
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
    except Exception as e:
        logger.error(f"❌ Error generando PDF: {str(e)}")
        return {'error': str(e)}, 500

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
        textColor=colors.HexColor('#E83E8C'),
        spaceAfter=20,
        alignment=1,
    ))
    
    styles.add(ParagraphStyle(
        name='Subtitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#B32D62'),
        spaceAfter=10,
    ))
    
    styles.add(ParagraphStyle(
        name='Disclaimer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#666666'),
        alignment=1,
    ))
    
    # TÍTULO
    title = Paragraph("🍈 Pitahaya Investments", styles['CustomTitle'])
    elements.append(title)
    
    subtitle = Paragraph(f"Simulación personalizada para: <b>{nombre}</b>", styles['Subtitle'])
    elements.append(subtitle)
    
    date_text = Paragraph(f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", styles['Normal'])
    elements.append(date_text)
    
    elements.append(Spacer(1, 0.3 * inch))
    
    # DATOS DE INVERSIÓN
    inv_data = [
        ["Concepto", "Valor"],
        ["Inversión inicial", f"${capital:,.0f}"],
        ["Plazo", f"{AÑOS} años"],
        ["Tasa Pitahaya (renta)", f"{RENTA_ANUAL*100:.1f}% anual"],
        ["Plusvalía estimada", f"{PLUSVALIA_FACTOR*100:.0f}% del capital"],
    ]
    
    inv_table = Table(inv_data, colWidths=[3*inch, 2.5*inch])
    inv_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#E83E8C')),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#FFB6C1')),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 1), (1, -1), 'Helvetica'),
    ]))
    
    elements.append(inv_table)
    elements.append(Spacer(1, 0.3 * inch))
    
    # COMPARATIVA
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
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#E83E8C')),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (1, 1), colors.HexColor('#FFF0F5')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#FFB6C1')),
    ]))
    
    elements.append(comp_table)
    elements.append(Spacer(1, 0.2 * inch))
    
    # DETALLE PITAHAYA
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
        ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#E83E8C')),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 4), (1, 4), colors.HexColor('#FFF0F5')),
        ('FONTNAME', (0, 4), (1, 4), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#FFB6C1')),
    ]))
    
    elements.append(detalle_table)
    elements.append(Spacer(1, 0.2 * inch))
    
    # ADVERTENCIA SOFIPOS
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
    
    # DESCARGO Y CONTACTO
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
    
    # MARCA DE AGUA
    def add_watermark(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica-Bold', 45)
        canvas.setFillColor(colors.HexColor('#cccccc'))
        canvas.setFillAlpha(0.3)
        canvas.rotate(45)
        canvas.drawString(150, -200, "PITAHAYA INVESTMENTS")
        canvas.drawString(150, -50, "PITAHAYA INVESTMENTS")
        canvas.drawString(150, 100, "PITAHAYA INVESTMENTS")
        canvas.drawString(150, 250, "PITAHAYA INVESTMENTS")
        canvas.drawString(150, 400, "PITAHAYA INVESTMENTS")
        canvas.drawString(150, 550, "PITAHAYA INVESTMENTS")
        canvas.restoreState()
    
    doc.build(
        elements,
        onFirstPage=add_watermark,
        onLaterPages=add_watermark
    )
    
    buffer.seek(0)
    return buffer

# ============================================
# IMPORTANTE: LÍNEA NECESARIA PARA VERCEL
# ============================================
app = app

# ============================================
# INICIAR APLICACIÓN (SOLO PARA DESARROLLO LOCAL)
# ============================================
if __name__ == '__main__':
    print("="*50)
    print("🍈 Pitahaya Investments - Calculadora")
    print("="*50)
    print("✅ Modo desarrollo local")
    print("✅ Auto-login con cookie habilitado")
    print("🌐 Servidor: http://localhost:5000")
    print("="*50)
    app.run(debug=True)