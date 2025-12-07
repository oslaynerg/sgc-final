import os
import io
import csv
import pandas as pd
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, make_response
from sqlalchemy import func
from dotenv import load_dotenv

# Importar db desde db.py
from db import db 

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)

# --- Configuración de la Aplicación ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'clave_secreta_por_defecto')

# Configuración Inteligente de Base de Datos (SQLite local / PostgreSQL Nube)
database_url = os.getenv('DATABASE_URL')

# 2. Si no existe (estamos en tu PC), usar SQLite
if not database_url:
    database_url = 'sqlite:///sgc.db'

# 3. CORRECCIÓN OBLIGATORIA: Cambiar postgres:// a postgresql://
# (Esto es lo que estaba fallando en el log)
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializar la DB
db.init_app(app) 

# ===================================================
# Importar modelos después de inicializar
# ===================================================
from models import (
    Estado, Municipio, Parroquia, AldeaUniversitaria, 
    Personal, Estudiante, Usuario, PermisoCoordinador, 
    Carrera, Cargo, Tramo, PeriodoAcademico
)

# ===================================================
# DECORADORES DE SEGURIDAD
# ===================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debe iniciar sesión para acceder a esta página.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def roles_required(roles):
    """Permite el acceso si el usuario tiene ALGUNO de los roles listados."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            
            user_rol = session.get('user_rol')
            if user_rol not in roles:
                flash('Acceso denegado. No tiene los permisos necesarios.', 'danger')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def role_required(role):
    """Atajo para requerir un solo rol específico."""
    return roles_required([role])

def get_user_permissions():
    """Retorna el primer permiso geográfico del Coordinador logueado."""
    if session.get('user_rol') == 'COORDINADOR':
        user_id = session['user_id']
        user = db.session.get(Usuario, user_id)
        if user and user.permisos:
            return user.permisos[0]
    return None

# ===================================================
# RUTAS PRINCIPALES
# ===================================================

@app.route('/')
def index():
    if 'user_id' not in session:
        return render_template('index.html')

    # Estadísticas para el Dashboard
    total_estudiantes = db.session.query(func.count(Estudiante.id)).scalar()
    total_personal = db.session.query(func.count(Personal.id)).scalar()
    total_aldeas = db.session.query(func.count(AldeaUniversitaria.id)).scalar()
    total_municipios = db.session.query(func.count(Municipio.id)).scalar()

    return render_template('index.html', 
                           total_estudiantes=total_estudiantes,
                           total_personal=total_personal,
                           total_aldeas=total_aldeas,
                           total_municipios=total_municipios)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nombre_usuario = request.form.get('nombre_usuario')
        password = request.form.get('password')
        
        user = Usuario.query.filter_by(_nombre_usuario=nombre_usuario.upper()).first()
        
        if user and user.verify_password(password):
            if not user.activo:
                flash('Su usuario está desactivado. Contacte al administrador.', 'warning')
                return redirect(url_for('login'))

            session['user_id'] = user.id
            session['user_rol'] = user.rol
            flash(f'Bienvenido, {user.nombre_usuario}.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Credenciales inválidas.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada exitosamente.', 'success')
    return redirect(url_for('index'))

# ===================================================
# GESTIÓN DE USUARIOS Y CONFIGURACIÓN
# ===================================================

@app.route('/super_registro', methods=['GET', 'POST'])
def super_registro():
    if Usuario.query.filter_by(_rol='SUPER_USUARIO').first():
        flash('El Super Usuario ya existe.', 'danger')
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        try:
            nuevo_usuario = Usuario(
                nombre_usuario=request.form.get('nombre_usuario'),
                email=request.form.get('email'),
                rol='SUPER_USUARIO'
            )
            nuevo_usuario.password = request.form.get('password')
            
            db.session.add(nuevo_usuario)
            db.session.commit()
            flash('¡Super Usuario creado! Inicie sesión.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            return render_template('super_registro.html', error=f"Error: {e}")

    return render_template('super_registro.html')

@app.route('/usuarios')
@role_required('SUPER_USUARIO')
def listar_usuarios():
    usuarios = Usuario.query.all()
    municipios = Municipio.query.all() 
    aldeas = AldeaUniversitaria.query.all()
    return render_template('listar_usuarios.html', usuarios=usuarios, municipios=municipios, aldeas=aldeas)

@app.route('/usuarios/agregar', methods=['GET', 'POST'])
@role_required('SUPER_USUARIO')
def agregar_usuario():
    ROLES_DISPONIBLES = ['ANALISTA', 'COORDINADOR'] 

    if request.method == 'POST':
        try:
            rol = request.form.get('rol')
            if rol == 'SUPER_USUARIO':
                flash('Acción no permitida.', 'danger')
                return redirect(url_for('listar_usuarios'))

            nuevo = Usuario(
                nombre_usuario=request.form.get('nombre_usuario'),
                email=request.form.get('email'),
                rol=rol
            )
            nuevo.password = request.form.get('password')
            
            db.session.add(nuevo)
            db.session.commit()
            flash('Usuario registrado.', 'success')
            return redirect(url_for('listar_usuarios'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", 'danger')

    return render_template('agregar_usuario.html', ROLES_DISPONIBLES=ROLES_DISPONIBLES)

@app.route('/usuarios/<int:user_id>/editar', methods=['GET', 'POST'])
@role_required('SUPER_USUARIO')
def editar_usuario(user_id):
    user = Usuario.query.get_or_404(user_id)
    ROLES_DISPONIBLES = ['SUPER_USUARIO', 'ANALISTA', 'COORDINADOR']
    
    if request.method == 'POST':
        user.email = request.form.get('email')
        nuevo_rol = request.form.get('rol')
        
        # Validación básica para no degradar al super usuario accidentalmente
        if user.rol == 'SUPER_USUARIO' and nuevo_rol != 'SUPER_USUARIO':
             flash('No puede cambiar el rol del Super Usuario principal.', 'danger')
        else:
             user.rol = nuevo_rol
             db.session.commit()
             flash('Usuario actualizado.', 'success')
             return redirect(url_for('listar_usuarios'))
            
    return render_template('editar_usuario.html', user=user, ROLES_DISPONIBLES=ROLES_DISPONIBLES)

@app.route('/usuarios/<int:user_id>/estado', methods=['POST'])
@role_required('SUPER_USUARIO')
def cambiar_estado_usuario(user_id):
    user = Usuario.query.get_or_404(user_id)
    if user.rol == 'SUPER_USUARIO':
        flash('No se puede desactivar al Super Usuario.', 'danger')
    else:
        user.activo = not user.activo
        db.session.commit()
        flash(f'Estado de {user.nombre_usuario} cambiado.', 'success')
    return redirect(url_for('listar_usuarios'))

@app.route('/usuarios/<int:user_id>/permisos', methods=['POST'])
@role_required('SUPER_USUARIO')
def gestionar_permisos(user_id):
    user = Usuario.query.get_or_404(user_id)
    municipio_id = request.form.get('municipio_id')
    aldea_id = request.form.get('aldea_id')
    
    if municipio_id or aldea_id:
        PermisoCoordinador.query.filter_by(usuario_id=user.id).delete()
        nuevo = PermisoCoordinador(
            usuario_id=user.id,
            municipio_id=municipio_id if municipio_id != 'None' else None,
            aldea_id=aldea_id if aldea_id != 'None' else None
        )
        db.session.add(nuevo)
        db.session.commit()
        flash('Permisos actualizados.', 'success')
    return redirect(url_for('listar_usuarios'))

@app.route('/setup_catalogos')
@role_required('SUPER_USUARIO')
def setup_catalogos():
    programas = {
        'PNF': ['INFORMATICA', 'ELECTRICIDAD', 'AGROALIMENTARIA', 'ENFERMERIA', 'CONSTRUCCION CIVIL'],
        'PFG': ['ESTUDIOS JURIDICOS', 'COMUNICACION SOCIAL', 'GESTION AMBIENTAL']
    }
    cargos = [
    'ASESOR JURÍDICO',
    'COORDINADOR DE ATENCIÓN AL TRIUNFADOR',
    'COORDINADOR DE ALDEA',
    'COORDINADOR DE DESARROLLO INSTITUCIONAL',
    'COORDINADOR DE EJE',
    'COORDINADOR DE PASANTIAS',
    'COORDINADOR DE PROCESOS Y GESTIÓN',
    'COORDINADOR DE PROYECTO',
    'COORDINADOR DE SALA SUCRE',
    'COORDINADOR DE SERVICIO COMUNITARIO',
    'COORDINADOR MUNICIPAL',
    'COORDINAR GENERAL',
    'DOCENTE',
    'ENLACE MUNICIPAL',
    'OPERARIO',
    'SECRETARIA',
    'VIGILANTE'
    ]
    tramos = ['TRAYECTO INICIAL', 'TRAYECTO I', 'TRAYECTO II', 'TRAYECTO III', 'TRAYECTO IV']
    periodos = ['2024-I', '2024-II', '2025-I']

    for tipo, lista in programas.items():
        for nom in lista:
            if not Carrera.query.filter_by(_nombre=nom, _tipo=tipo).first():
                db.session.add(Carrera(tipo=tipo, nombre=nom))
    
    for c in cargos:
        if not Cargo.query.filter_by(_nombre=c).first():
            db.session.add(Cargo(nombre=c))
            
    for t in tramos:
        if not Tramo.query.filter_by(nombre=t).first():
            db.session.add(Tramo(nombre=t))
            
    for p in periodos:
        if not PeriodoAcademico.query.filter_by(nombre=p).first():
            db.session.add(PeriodoAcademico(nombre=p))

    db.session.commit()
    flash('Catálogos actualizados.', 'success')
    return redirect(url_for('index'))

@app.route('/configuracion/academica', methods=['GET', 'POST'])
@login_required
@role_required('SUPER_USUARIO')
def gestion_academica():
    if request.method == 'POST':
        tipo = request.form.get('tipo_accion')
        nombre = request.form.get('nombre').strip().upper()
        
        if not nombre:
            flash('El nombre no puede estar vacío.', 'danger')
        else:
            try:
                if tipo == 'nuevo_tramo':
                    if not Tramo.query.filter_by(nombre=nombre).first():
                        db.session.add(Tramo(nombre=nombre))
                        db.session.commit()
                        flash(f'Tramo "{nombre}" agregado.', 'success')
                    else:
                        flash('Ese Tramo ya existe.', 'warning')
                        
                elif tipo == 'nuevo_periodo':
                    if not PeriodoAcademico.query.filter_by(nombre=nombre).first():
                        db.session.add(PeriodoAcademico(nombre=nombre))
                        db.session.commit()
                        flash(f'Período "{nombre}" agregado.', 'success')
                    else:
                        flash('Ese Período ya existe.', 'warning')
            except Exception as e:
                db.session.rollback()
                flash(f'Error: {e}', 'danger')
                
    tramos = Tramo.query.order_by(Tramo.nombre).all()
    periodos = PeriodoAcademico.query.order_by(PeriodoAcademico.nombre.desc()).all()
    
    return render_template('gestion_academica.html', tramos=tramos, periodos=periodos)

@app.route('/configuracion/tramo/<int:id>/editar', methods=['POST'])
@role_required('SUPER_USUARIO')
def editar_tramo(id):
    tramo = Tramo.query.get_or_404(id)
    nuevo_nombre = request.form.get('nombre').strip().upper()
    
    if nuevo_nombre:
        try:
            tramo.nombre = nuevo_nombre
            db.session.commit()
            flash('Tramo actualizado.', 'success')
        except:
            db.session.rollback()
            flash('Error: Nombre duplicado o inválido.', 'danger')
    
    return redirect(url_for('gestion_academica'))

@app.route('/configuracion/tramo/<int:id>/eliminar', methods=['POST'])
@role_required('SUPER_USUARIO')
def eliminar_tramo(id):
    tramo = Tramo.query.get_or_404(id)
    # Verificar si está en uso
    if tramo.estudiantes:
        flash(f'No se puede eliminar "{tramo.nombre}" porque hay estudiantes asignados a él.', 'danger')
    else:
        db.session.delete(tramo)
        db.session.commit()
        flash('Tramo eliminado.', 'success')
    return redirect(url_for('gestion_academica'))

@app.route('/configuracion/periodo/<int:id>/editar', methods=['POST'])
@role_required('SUPER_USUARIO')
def editar_periodo(id):
    periodo = PeriodoAcademico.query.get_or_404(id)
    nuevo_nombre = request.form.get('nombre').strip().upper()
    
    if nuevo_nombre:
        try:
            periodo.nombre = nuevo_nombre
            db.session.commit()
            flash('Período actualizado.', 'success')
        except:
            db.session.rollback()
            flash('Error: Nombre duplicado o inválido.', 'danger')
            
    return redirect(url_for('gestion_academica'))

@app.route('/configuracion/periodo/<int:id>/eliminar', methods=['POST'])
@role_required('SUPER_USUARIO')
def eliminar_periodo(id):
    periodo = PeriodoAcademico.query.get_or_404(id)
    # Verificar uso
    if periodo.estudiantes:
        flash(f'No se puede eliminar "{periodo.nombre}" porque hay estudiantes inscritos en él.', 'danger')
    else:
        db.session.delete(periodo)
        db.session.commit()
        flash('Período eliminado.', 'success')
    return redirect(url_for('gestion_academica'))    

# ===================================================
# GESTIÓN GEOGRÁFICA (CRUD)
# ===================================================

@app.route('/estados')
@login_required
def listar_estados():
    return render_template('estados.html', estados=Estado.query.all())

@app.route('/estados/agregar', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA'])
def agregar_estado():
    if request.method == 'POST':
        try:
            db.session.add(Estado(nombre=request.form.get('nombre')))
            db.session.commit()
            return redirect(url_for('listar_estados'))
        except:
            db.session.rollback()
    return render_template('agregar_estado.html')

@app.route('/estados/<int:estado_id>/editar', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA'])
def editar_estado(estado_id):
    estado = Estado.query.get_or_404(estado_id)
    if request.method == 'POST':
        estado.nombre = request.form.get('nombre')
        db.session.commit()
        return redirect(url_for('listar_estados'))
    return render_template('editar_estado.html', estado=estado)

@app.route('/estados/<int:estado_id>/eliminar', methods=['POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA'])
def eliminar_estado(estado_id):
    estado = Estado.query.get_or_404(estado_id)
    
    # PROTECCIÓN: No borrar si tiene municipios
    if estado.municipios:
        flash(f'⚠️ No se puede borrar el Estado "{estado.nombre}" porque tiene {len(estado.municipios)} municipios registrados.', 'danger')
        return redirect(url_for('listar_estados'))

    try:
        db.session.delete(estado)
        db.session.commit()
        flash('Estado eliminado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar: {e}', 'danger')
        
    return redirect(url_for('listar_estados'))

@app.route('/estados/<int:estado_id>/municipios')
@login_required
def listar_municipios(estado_id):
    estado = Estado.query.get_or_404(estado_id)
    return render_template('municipios.html', estado=estado, municipios=estado.municipios)

@app.route('/municipios/<int:municipio_id>/editar', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA'])
def editar_municipio(municipio_id):
    municipio = Municipio.query.get_or_404(municipio_id)
    
    if request.method == 'POST':
        nuevo_nombre = request.form.get('nombre')
        if nuevo_nombre:
            try:
                municipio.nombre = nuevo_nombre
                db.session.commit()
                flash(f'Municipio "{municipio.nombre}" actualizado correctamente.', 'success')
                return redirect(url_for('listar_municipios', estado_id=municipio.estado_id))
            except Exception as e:
                db.session.rollback()
                flash(f'Error al actualizar el municipio: {e}', 'danger')
        else:
            flash('El nombre del municipio no puede estar vacío.', 'danger')
            
    return render_template('editar_municipio.html', municipio=municipio)

@app.route('/estados/<int:estado_id>/municipios/agregar', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA'])
def agregar_municipio(estado_id):
    estado = Estado.query.get_or_404(estado_id)
    if request.method == 'POST':
        db.session.add(Municipio(nombre=request.form.get('nombre'), estado_id=estado.id))
        db.session.commit()
        return redirect(url_for('listar_municipios', estado_id=estado.id))
    return render_template('agregar_municipio.html', estado=estado)

@app.route('/municipios/<int:municipio_id>/eliminar', methods=['POST'])
@roles_required(['SUPER_USUARIO'])
def eliminar_municipio(municipio_id):
    municipio = Municipio.query.get_or_404(municipio_id)
    if municipio.parroquias:
        flash('No se puede borrar: Tiene parroquias asociadas.', 'danger')
    else:
        db.session.delete(municipio)
        db.session.commit()
        flash('Municipio eliminado.', 'success')
    return redirect(url_for('listar_municipios', estado_id=municipio.estado_id))

@app.route('/municipios/<int:municipio_id>/parroquias')
@login_required
def listar_parroquias(municipio_id):
    municipio = Municipio.query.get_or_404(municipio_id)
    return render_template('parroquias.html', municipio=municipio, parroquias=municipio.parroquias)

@app.route('/municipios/<int:municipio_id>/parroquias/agregar', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA'])
def agregar_parroquia(municipio_id):
    municipio = Municipio.query.get_or_404(municipio_id)
    if request.method == 'POST':
        db.session.add(Parroquia(nombre=request.form.get('nombre'), municipio_id=municipio.id))
        db.session.commit()
        return redirect(url_for('listar_parroquias', municipio_id=municipio.id))
    return render_template('agregar_parroquia.html', municipio=municipio)

@app.route('/parroquias/<int:parroquia_id>/editar', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA'])
def editar_parroquia(parroquia_id):
    parroquia = Parroquia.query.get_or_404(parroquia_id)
    
    if request.method == 'POST':
        nuevo_nombre = request.form.get('nombre')
        if nuevo_nombre:
            try:
                parroquia.nombre = nuevo_nombre
                db.session.commit()
                flash(f'Parroquia "{parroquia.nombre}" actualizada correctamente.', 'success')
                return redirect(url_for('listar_parroquias', municipio_id=parroquia.municipio_id))
            except Exception as e:
                db.session.rollback()
                flash(f'Error al actualizar la parroquia: {e}', 'danger')
        else:
            flash('El nombre de la parroquia no puede estar vacío.', 'danger')
            
    return render_template('editar_parroquia.html', parroquia=parroquia)

@app.route('/parroquias/<int:parroquia_id>/eliminar', methods=['POST'])
@roles_required(['SUPER_USUARIO'])
def eliminar_parroquia(parroquia_id):
    parroquia = Parroquia.query.get_or_404(parroquia_id)
    if parroquia.aldeas:
        flash('No se puede borrar: Tiene aldeas asociadas.', 'danger')
    else:
        db.session.delete(parroquia)
        db.session.commit()
        flash('Parroquia eliminada.', 'success')
    return redirect(url_for('listar_parroquias', municipio_id=parroquia.municipio_id))

@app.route('/parroquias/<int:parroquia_id>/aldeas')
@login_required
def listar_aldeas(parroquia_id):
    parroquia = Parroquia.query.get_or_404(parroquia_id)
    return render_template('aldeas.html', parroquia=parroquia, aldeas=parroquia.aldeas)

@app.route('/parroquias/<int:parroquia_id>/aldeas/agregar', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA'])
def agregar_aldea(parroquia_id):
    parroquia = Parroquia.query.get_or_404(parroquia_id)
    if request.method == 'POST':
        try:
            nuevo = AldeaUniversitaria(
                nombre=request.form.get('nombre'),
                codigo=request.form.get('codigo'),
                parroquia_id=parroquia.id
            )
            db.session.add(nuevo)
            db.session.commit()
            return redirect(url_for('listar_aldeas', parroquia_id=parroquia.id))
        except:
            db.session.rollback()
            return render_template('agregar_aldea.html', parroquia=parroquia, error="Error o Código duplicado.")
    return render_template('agregar_aldea.html', parroquia=parroquia)

@app.route('/aldeas/<int:aldea_id>/editar', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA'])
def editar_aldea(aldea_id):
    aldea = AldeaUniversitaria.query.get_or_404(aldea_id)
    if request.method == 'POST':
        aldea.nombre = request.form.get('nombre')
        aldea.codigo = request.form.get('codigo')
        db.session.commit()
        return redirect(url_for('listar_aldeas', parroquia_id=aldea.parroquia_id))
    return render_template('editar_aldea.html', aldea=aldea)

@app.route('/aldeas/<int:aldea_id>/eliminar', methods=['POST'])
@roles_required(['SUPER_USUARIO'])
def eliminar_aldea(aldea_id):
    aldea = AldeaUniversitaria.query.get_or_404(aldea_id)
    if aldea.estudiantes or aldea.personal:
        flash('No se puede borrar: Tiene personas registradas.', 'danger')
    else:
        db.session.delete(aldea)
        db.session.commit()
        flash('Aldea eliminada.', 'success')
    return redirect(url_for('listar_aldeas', parroquia_id=aldea.parroquia_id))

# ===================================================
# GESTIÓN DE PERSONAL Y ESTUDIANTES
# ===================================================

@app.route('/aldeas/<int:aldea_id>/personal')
@login_required
def listar_personal(aldea_id):
    aldea = AldeaUniversitaria.query.get_or_404(aldea_id)
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '', type=str)
    
    query = Personal.query.filter_by(aldea_id=aldea_id)
    
    if search:
        pat = f'%{search.upper()}%'
        query = query.filter((Personal.numero_documento.like(pat)) | (Personal._nombre_apellido.like(pat)))
        
    personal_list = query.order_by(Personal._nombre_apellido).paginate(page=page, per_page=10)
    return render_template('personal.html', aldea=aldea, personal_list=personal_list, search_query=search)

@app.route('/aldeas/<int:aldea_id>/personal/agregar', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA', 'COORDINADOR'])
def agregar_personal(aldea_id):
    aldea = db.session.get(AldeaUniversitaria, aldea_id)
    cargos = Cargo.query.order_by(Cargo._nombre).all()
    
    if request.method == 'POST':
        try:
            fecha_str = request.form.get('fecha_nacimiento')
            nuevo = Personal(
                tipo_documento=request.form.get('tipo_documento'),
                numero_documento=request.form.get('numero_documento'),
                nombre_apellido=request.form.get('nombre_apellido'),
                correo=request.form.get('correo'),
                telefono=request.form.get('telefono'),
                fecha_nacimiento=datetime.strptime(fecha_str, '%Y-%m-%d').date() if fecha_str else None,
                genero=request.form.get('genero'),
                cargo_id=request.form.get('cargo_id'),
                tipo_personal=request.form.get('tipo_personal'),
                aldea_id=aldea.id
            )
            db.session.add(nuevo)
            db.session.commit()
            flash('Personal agregado.', 'success')
            return redirect(url_for('listar_personal', aldea_id=aldea.id))
        except Exception as e:
            db.session.rollback()
            return render_template('agregar_personal.html', aldea=aldea, cargos=cargos, error=f"Error: {e}")
            
    return render_template('agregar_personal.html', aldea=aldea, cargos=cargos)

@app.route('/personal/<int:personal_id>/editar', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA', 'COORDINADOR'])
def editar_personal(personal_id):
    p = db.session.get(Personal, personal_id)
    cargos = Cargo.query.all()
    
    if request.method == 'POST':
        p.numero_documento = request.form.get('numero_documento')
        p.nombre_apellido = request.form.get('nombre_apellido')
        p.cargo_id = request.form.get('cargo_id')
        # ... (Actualizar resto de campos si es necesario)
        db.session.commit()
        return redirect(url_for('listar_personal', aldea_id=p.aldea_id))
        
    return render_template('editar_personal.html', personal=p, cargos=cargos)

@app.route('/personal/<int:personal_id>/eliminar', methods=['POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA', 'COORDINADOR'])
def eliminar_personal(personal_id):
    p = Personal.query.get_or_404(personal_id)
    aid = p.aldea_id
    db.session.delete(p)
    db.session.commit()
    flash('Personal eliminado.', 'success')
    return redirect(url_for('listar_personal', aldea_id=aid))

# --- ESTUDIANTES ---

@app.route('/aldeas/<int:aldea_id>/estudiantes')
@login_required
def listar_estudiantes(aldea_id):
    aldea = AldeaUniversitaria.query.get_or_404(aldea_id)
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '', type=str)
    
    query = Estudiante.query.filter_by(aldea_id=aldea_id)
    if search:
        pat = f'%{search.upper()}%'
        query = query.filter((Estudiante.numero_documento.like(pat)) | (Estudiante._nombre_apellido.like(pat)))
        
    est_list = query.order_by(Estudiante._nombre_apellido).paginate(page=page, per_page=10)
    return render_template('estudiantes.html', aldea=aldea, estudiantes_list=est_list, search_query=search)

@app.route('/aldeas/<int:aldea_id>/estudiantes/agregar', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA', 'COORDINADOR'])
def agregar_estudiante(aldea_id):
    aldea = db.session.get(AldeaUniversitaria, aldea_id)
    tramos = Tramo.query.all()
    periodos = PeriodoAcademico.query.order_by(PeriodoAcademico.nombre.desc()).all()

    if request.method == 'POST':
        try:
            f_str = request.form.get('fecha_nacimiento')
            nuevo = Estudiante(
                tipo_documento=request.form.get('tipo_documento'),
                numero_documento=request.form.get('numero_documento'),
                nombre_apellido=request.form.get('nombre_apellido'),
                correo=request.form.get('correo'),
                telefono=request.form.get('telefono'),
                fecha_nacimiento=datetime.strptime(f_str, '%Y-%m-%d').date() if f_str else None,
                genero=request.form.get('genero'),
                carrera_id=request.form.get('carrera_id'),
                tramo_id=request.form.get('tramo_id'),
                periodo_id=request.form.get('periodo_id'),
                aldea_id=aldea.id
            )
            db.session.add(nuevo)
            db.session.commit()
            flash('Estudiante agregado.', 'success')
            return redirect(url_for('listar_estudiantes', aldea_id=aldea.id))
        except Exception as e:
            db.session.rollback()
            return render_template('agregar_estudiante.html', aldea=aldea, tramos=tramos, periodos=periodos, error=f"Error: {e}")

    return render_template('agregar_estudiante.html', aldea=aldea, tramos=tramos, periodos=periodos)

@app.route('/estudiantes/<int:estudiante_id>/editar', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA', 'COORDINADOR'])
def editar_estudiante(estudiante_id):
    est = db.session.get(Estudiante, estudiante_id)
    tramos = Tramo.query.all()
    periodos = PeriodoAcademico.query.all()
    carreras = Carrera.query.all() # Necesario para mostrar la actual
    
    if request.method == 'POST':
        est.numero_documento = request.form.get('numero_documento')
        est.nombre_apellido = request.form.get('nombre_apellido')
        est.carrera_id = request.form.get('carrera_id')
        est.tramo_id = request.form.get('tramo_id')
        est.periodo_id = request.form.get('periodo_id')
        # ... actualizar resto ...
        db.session.commit()
        return redirect(url_for('listar_estudiantes', aldea_id=est.aldea_id))
        
    return render_template('editar_estudiante.html', estudiante=est, tramos=tramos, periodos=periodos, carreras=carreras)

@app.route('/estudiantes/<int:estudiante_id>/eliminar', methods=['POST'])
@roles_required(['SUPER_USUARIO', 'ANALISTA', 'COORDINADOR'])
def eliminar_estudiante(estudiante_id):
    e = Estudiante.query.get_or_404(estudiante_id)
    aid = e.aldea_id
    db.session.delete(e)
    db.session.commit()
    flash('Estudiante eliminado.', 'success')
    return redirect(url_for('listar_estudiantes', aldea_id=aid))

# ===================================================
# REPORTES Y CARGA MASIVA
# ===================================================

@app.route('/descargar_plantilla_estudiantes')
@login_required
def descargar_plantilla_estudiantes():
    # Plantilla actualizada con las columnas correctas
    df = pd.DataFrame({
        'TIPO_DOC': ['V', 'E'],
        'NUMERO_DOC': ['12345678', '87654321'],
        'NOMBRE_APELLIDO': ['JUAN PEREZ', 'MARIA GOMEZ'],
        'GENERO': ['MASCULINO', 'FEMENINO'],
        'FECHA_NACIMIENTO': ['31/01/2000', '12/06/1998'],
        'TELEFONO': ['04121234567', '04149998877'],
        'CORREO': ['juan@example.com', 'maria@example.com'],
        'NOMBRE_CARRERA': ['INFORMATICA', 'ELECTRICIDAD'],
        'CODIGO_ALDEA': ['A001', 'A001'],
        'TRAMO': ['TRAYECTO I', 'TRAYECTO II'],
        'PERIODO': ['2025-I', '2025-I']
    })
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Plantilla')
    output.seek(0)
    return send_file(output, download_name="plantilla_estudiantes.xlsx", as_attachment=True)

@app.route('/importar/estudiantes', methods=['GET', 'POST'])
@roles_required(['SUPER_USUARIO'])
def importar_estudiantes():
    # 1. Cargar datos para mostrar la "Guía de Datos" en el HTML
    tramos_activos = Tramo.query.order_by(Tramo.nombre).all()
    periodos_activos = PeriodoAcademico.query.order_by(PeriodoAcademico.nombre.desc()).all()

    if request.method == 'POST':
        file = request.files.get('archivo_excel')
        if not file or not file.filename.endswith('.xlsx'):
            flash('⚠️ Archivo inválido. Debe ser .xlsx', 'danger')
            return redirect(request.url)
            
        try:
            df = pd.read_excel(file)
            # Limpiar cabeceras (quitar espacios y poner mayúsculas)
            df.columns = [str(c).strip().upper() for c in df.columns]
            
            # Verificar columnas mínimas
            requeridos = ['NUMERO_DOC', 'NOMBRE_CARRERA', 'CODIGO_ALDEA', 'TRAMO', 'PERIODO']
            faltantes = [col for col in requeridos if col not in df.columns]
            
            if faltantes:
                flash(f'⛔ Faltan columnas en el Excel: {", ".join(faltantes)}', 'danger')
                return redirect(request.url)

            exitos, errores = 0, []
            
            for idx, row in df.iterrows():
                linea = idx + 2 # Fila real en Excel
                try:
                    # Leer datos limpios
                    ndoc = str(row.get('NUMERO_DOC', '')).split('.')[0].strip()
                    tipo_doc = str(row.get('TIPO_DOC', 'V')).strip().upper()
                    nombre = str(row.get('NOMBRE_APELLIDO', '')).strip().upper()
                    
                    caldea = str(row.get('CODIGO_ALDEA', '')).strip().upper()
                    ncarrera = str(row.get('NOMBRE_CARRERA', '')).strip().upper()
                    
                    ntramo = str(row.get('TRAMO', '')).strip().upper()
                    nperiodo = str(row.get('PERIODO', '')).strip().upper()
                    
                    # Validación básica de campos vacíos
                    if not ndoc or not caldea or not ncarrera:
                        errores.append(f"Fila {linea}: Faltan datos obligatorios (Cédula, Aldea o Carrera).")
                        continue 
                        
                    # --- BLINDAJE: VALIDAR EXISTENCIA EN BD ---
                    
                    # 1. Aldea
                    aldea = AldeaUniversitaria.query.filter_by(_codigo=caldea).first()
                    if not aldea:
                        errores.append(f"Fila {linea}: Código de Aldea '{caldea}' no existe.")
                        continue

                    # 2. Carrera (Búsqueda exacta)
                    carrera = Carrera.query.filter_by(_nombre=ncarrera).first()
                    if not carrera:
                        errores.append(f"Fila {linea}: Carrera '{ncarrera}' no existe en el catálogo.")
                        continue

                    # 3. Tramo (Búsqueda exacta)
                    tramo = Tramo.query.filter_by(nombre=ntramo).first()
                    if not tramo:
                        errores.append(f"Fila {linea}: Tramo '{ntramo}' no es válido. Verifique la lista.")
                        continue

                    # 4. Período (Búsqueda exacta)
                    per = PeriodoAcademico.query.filter_by(nombre=nperiodo).first()
                    if not per:
                        errores.append(f"Fila {linea}: Período '{nperiodo}' no es válido.")
                        continue
                        
                    # 5. Duplicidad de estudiante
                    if Estudiante.query.filter_by(numero_documento=ndoc, tipo_documento=tipo_doc).first():
                        errores.append(f"Fila {linea}: Estudiante {ndoc} ya existe.")
                        continue
                    
                    # --- CREACIÓN ---
                    
                    # Procesar fecha opcional
                    fecha_nac = None
                    if pd.notnull(row.get('FECHA_NACIMIENTO')):
                        try: fecha_nac = pd.to_datetime(row.get('FECHA_NACIMIENTO')).date()
                        except: pass

                    new_st = Estudiante(
                        tipo_documento=tipo_doc,
                        numero_documento=ndoc,
                        nombre_apellido=nombre,
                        correo=str(row.get('CORREO', '')).strip(),
                        telefono=str(row.get('TELEFONO', '')).strip(),
                        fecha_nacimiento=fecha_nac,
                        genero=str(row.get('GENERO', '')).strip().upper(),
                        
                        # Asignamos los IDs encontrados
                        carrera_id=carrera.id,
                        aldea_id=aldea.id,
                        tramo_id=tramo.id,
                        periodo_id=per.id,
                        
                        cargado_por='CARGA_MASIVA'
                    )
                    db.session.add(new_st)
                    exitos += 1
                    
                except Exception as e:
                    errores.append(f"Fila {linea}: Error interno ({str(e)})")
            
            # Confirmar cambios si hubo éxitos
            if exitos > 0:
                db.session.commit()
                flash(f'✅ Importación finalizada. Registrados: {exitos}.', 'success')
            
            # Mostrar errores (Limitado a 10 para no saturar)
            if errores:
                msg = "<br>".join(errores[:10])
                if len(errores) > 10: msg += f"<br>... y {len(errores)-10} errores más."
                flash(f'⚠️ Se encontraron errores en {len(errores)} filas:<br>{msg}', 'warning')
                
        except Exception as e:
            flash(f'⛔ Error crítico procesando archivo: {e}', 'danger')
            
    # PASAR LAS LISTAS AL TEMPLATE PARA LA "GUÍA DE DATOS"
    return render_template('importar.html', tramos=tramos_activos, periodos=periodos_activos)
    if request.method == 'POST':
        file = request.files.get('archivo_excel')
        if not file or not file.filename.endswith('.xlsx'):
            flash('Archivo inválido.', 'danger')
            return redirect(request.url)
            
        try:
            df = pd.read_excel(file)
            df.columns = [str(c).strip().upper() for c in df.columns]
            
            exitos, errores = 0, []
            
            for idx, row in df.iterrows():
                try:
                    linea = idx + 2
                    ndoc = str(row.get('NUMERO_DOC', '')).split('.')[0].strip()
                    caldea = str(row.get('CODIGO_ALDEA', '')).strip().upper()
                    ncarrera = str(row.get('NOMBRE_CARRERA', '')).strip().upper()
                    ntramo = str(row.get('TRAMO', '')).strip().upper()
                    nperiodo = str(row.get('PERIODO', '')).strip().upper()
                    
                    if not ndoc or not caldea or not ncarrera:
                        continue 
                        
                    # Validar existencias
                    aldea = AldeaUniversitaria.query.filter_by(_codigo=caldea).first()
                    carrera = Carrera.query.filter_by(_nombre=ncarrera).first()
                    tramo = Tramo.query.filter_by(nombre=ntramo).first()
                    per = PeriodoAcademico.query.filter_by(nombre=nperiodo).first()
                    
                    if not aldea or not carrera or not tramo or not per:
                        errores.append(f"Fila {linea}: Datos referenciales no encontrados.")
                        continue
                        
                    if Estudiante.query.filter_by(numero_documento=ndoc).first():
                        errores.append(f"Fila {linea}: Estudiante ya existe.")
                        continue
                        
                    # Crear
                    new_st = Estudiante(
                        tipo_documento=str(row.get('TIPO_DOC', 'V')).strip().upper(),
                        numero_documento=ndoc,
                        nombre_apellido=str(row.get('NOMBRE_APELLIDO', '')).strip().upper(),
                        carrera_id=carrera.id,
                        aldea_id=aldea.id,
                        tramo_id=tramo.id,
                        periodo_id=per.id,
                        cargado_por='CARGA_MASIVA'
                    )
                    db.session.add(new_st)
                    exitos += 1
                    
                except Exception as e:
                    errores.append(f"Error fila {idx+2}: {e}")
            
            if exitos > 0:
                db.session.commit()
                flash(f'Importados {exitos} registros.', 'success')
            if errores:
                flash(f'Errores: {len(errores)}.', 'warning')
                
        except Exception as e:
            flash(f'Error procesando archivo: {e}', 'danger')
            
    return render_template('importar.html')

@app.route('/reportes', methods=['GET', 'POST'])
@login_required
def reportes():
    # Cargar listas para filtros
    estados = Estado.query.order_by(Estado._nombre).all()
    carreras = Carrera.query.order_by(Carrera._nombre).all()
    cargos = Cargo.query.order_by(Cargo._nombre).all()
    
    # Variable única para los resultados
    resultados = []
    tipo_reporte = 'estudiantes' 
    
    if request.method == 'POST':
        tipo_reporte = request.form.get('tipo_reporte')
        accion = request.form.get('accion')
        
        # Filtros
        tipo_documento = request.form.get('tipo_documento')
        estado_id = request.form.get('estado_id')
        municipio_id = request.form.get('municipio_id')
        parroquia_id = request.form.get('parroquia_id')
        aldea_id = request.form.get('aldea_id')
        genero = request.form.get('genero')
        carrera_id = request.form.get('carrera_id')
        cargo_id = request.form.get('cargo_id')
        
        query = None

        # 1. Construir Query Base
        if tipo_reporte == 'estudiantes':
            query = Estudiante.query.join(AldeaUniversitaria).join(Parroquia).join(Municipio)
            if carrera_id: query = query.filter(Estudiante.carrera_id == carrera_id)
            if genero: query = query.filter(Estudiante._genero == genero)
            if tipo_documento: query = query.filter(Estudiante.tipo_documento == tipo_documento)
            
        elif tipo_reporte == 'personal':
            query = Personal.query.join(AldeaUniversitaria).join(Parroquia).join(Municipio)
            if cargo_id: query = query.filter(Personal.cargo_id == cargo_id)
            if genero: query = query.filter(Personal._genero == genero)
            if tipo_documento: query = query.filter(Personal.tipo_documento == tipo_documento)

        # 2. Aplicar Filtros Geográficos
        if query:
            if estado_id: query = query.filter(Municipio.estado_id == estado_id)
            if municipio_id: query = query.filter(Parroquia.municipio_id == municipio_id)
            if parroquia_id: query = query.filter(AldeaUniversitaria.parroquia_id == parroquia_id)
            
            if aldea_id:
                if tipo_reporte == 'estudiantes':
                    query = query.filter(Estudiante.aldea_id == aldea_id)
                else:
                    query = query.filter(Personal.aldea_id == aldea_id)
            
            # ¡AQUÍ ESTABA EL ERROR! Usamos 'resultados' en lugar de 'res'
            resultados = query.all()

        # 3. Exportar Excel
        if accion == 'exportar':
            si = io.StringIO()
            cw = csv.writer(si)
            
            if tipo_reporte == 'estudiantes':
                cw.writerow(['Tipo', 'Cédula', 'Nombre', 'Programa', 'Carrera', 'Tramo', 'Periodo', 'Genero', 'Edad', 'Telefono', 'Correo', 'Estado', 'Municipio', 'Parroquia', 'Aldea'])
                for r in resultados:
                    cw.writerow([r.tipo_documento, r.numero_documento, r.nombre_apellido, r.carrera.tipo, r.carrera.nombre, r.nombre_tramo, r.nombre_periodo, r.genero, r.edad, r.telefono, r.correo, r.aldea.parroquia.municipio.estado.nombre, r.aldea.parroquia.municipio.nombre, r.aldea.parroquia.nombre, r.aldea.nombre])
            else:
                cw.writerow(['Tipo', 'Cédula', 'Nombre', 'Cargo', 'Tipo Personal', 'Genero', 'Edad', 'Telefono', 'Correo', 'Estado', 'Municipio', 'Parroquia', 'Aldea'])
                for r in resultados:
                    cw.writerow([r.tipo_documento, r.numero_documento, r.nombre_apellido, r.cargo.nombre, r.tipo_personal, r.genero, r.edad, r.telefono, r.correo, r.aldea.parroquia.municipio.estado.nombre, r.aldea.parroquia.municipio.nombre, r.aldea.parroquia.nombre, r.aldea.nombre])
            
            output = make_response(si.getvalue())
            output.headers["Content-Disposition"] = f"attachment; filename=reporte_{tipo_reporte}.csv"
            output.headers["Content-type"] = "text/csv"
            return output

    return render_template('reportes.html', 
                           estados=estados, 
                           carreras=carreras, 
                           cargos=cargos, 
                           resultados=resultados, # Ahora sí lleva datos
                           tipo_reporte=tipo_reporte)

# ===================================================
# APIS JSON (Para los selectores dinámicos)
# ===================================================

@app.route('/api/estados/<int:id>/municipios')
@login_required
def api_muni(id):
    # Usamos filter_by y order_by correctamente
    data = Municipio.query.filter_by(estado_id=id).order_by(Municipio._nombre).all()
    return jsonify([{'id': m.id, 'nombre': m.nombre} for m in data])

@app.route('/api/municipios/<int:id>/parroquias')
@login_required
def api_parro(id):
    data = Parroquia.query.filter_by(municipio_id=id).order_by(Parroquia._nombre).all()
    return jsonify([{'id': p.id, 'nombre': p.nombre} for p in data])

@app.route('/api/parroquias/<int:id>/aldeas')
@login_required
def api_aldea(id):
    data = AldeaUniversitaria.query.filter_by(parroquia_id=id).order_by(AldeaUniversitaria._nombre).all()
    return jsonify([{'id': a.id, 'nombre': a.nombre} for a in data])

@app.route('/api/carreras/<string:tipo>')
@login_required
def api_carreras(tipo):
    data = Carrera.query.filter_by(_tipo=tipo.upper()).order_by(Carrera._nombre).all()
    return jsonify([{'id': c.id, 'nombre': c.nombre} for c in data])

# ===================================================
# MANEJO DE ERRORES Y ARRANQUE
# ===================================================

@app.errorhandler(404)
def error_404(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def error_500(e):
    db.session.rollback()
    return render_template('errors/500.html'), 500

# Inicialización de Tablas (Vital para Railway)
with app.app_context():
    db.create_all()
    print(">>> Base de datos verificada/creada exitosamente <<<")

@app.route('/fuerza_bruta_db')
def fuerza_bruta_db():
    try:
        db.create_all()
        return "<h1>¡Tablas Creadas Exitosamente en PostgreSQL! 🚀</h1><p>Ahora intenta registrarte en /super_registro</p>"
    except Exception as e:
        return f"<h1>Error creando tablas:</h1><p>{str(e)}</p>"

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'favicon'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    app.run(debug=True)