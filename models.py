# models.py (OPTIMIZADO Y REORDENADO)
from db import db 
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# =========================================================
# 1. CATÁLOGOS Y TABLAS MAESTRAS (Independientes)
# =========================================================

class Carrera(db.Model):
    """Catálogo de Programas Académicos (PNF/PFG)"""
    id = db.Column(db.Integer, primary_key=True)
    _nombre = db.Column('nombre', db.String(100), nullable=False)
    _tipo = db.Column('tipo', db.String(10), nullable=False) # PNF o PFG
    
    estudiantes = db.relationship('Estudiante', backref='carrera', lazy=True)

    @property
    def nombre(self): return self._nombre
    @nombre.setter
    def nombre(self, value): self._nombre = value.upper() if value else None

    @property
    def tipo(self): return self._tipo
    @tipo.setter
    def tipo(self, value): self._tipo = value.upper() if value else None
    
    @property
    def nombre_completo(self):
        return f"{self.tipo} EN {self.nombre}"

class Cargo(db.Model):
    """Catálogo de Cargos Laborales"""
    id = db.Column(db.Integer, primary_key=True)
    _nombre = db.Column('nombre', db.String(100), unique=True, nullable=False)
    
    personal = db.relationship('Personal', backref='cargo', lazy=True)

    @property
    def nombre(self): return self._nombre
    @nombre.setter
    def nombre(self, value): self._nombre = value.upper() if value else None

class Tramo(db.Model):
    """Catálogo de Tramos/Trayectos"""
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    
    estudiantes = db.relationship('Estudiante', backref='tramo_obj', lazy=True)

class PeriodoAcademico(db.Model):
    """Catálogo de Períodos (2024-I, etc)"""
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    
    estudiantes = db.relationship('Estudiante', backref='periodo_obj', lazy=True)

# =========================================================
# 2. ESTRUCTURA GEOGRÁFICA (Jerarquía)
# =========================================================

class Estado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    _nombre = db.Column('nombre', db.String(50), nullable=False, unique=True)
    
    municipios = db.relationship('Municipio', backref='estado', lazy=True)

    @property
    def nombre(self): return self._nombre
    @nombre.setter
    def nombre(self, value): self._nombre = value.upper() if value else None

    def __repr__(self): return f'<Estado {self.nombre}>'

class Municipio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    _nombre = db.Column('nombre', db.String(50), nullable=False)
    estado_id = db.Column(db.Integer, db.ForeignKey('estado.id'), nullable=False)
    
    parroquias = db.relationship('Parroquia', backref='municipio', lazy=True)

    @property
    def nombre(self): return self._nombre
    @nombre.setter
    def nombre(self, value): self._nombre = value.upper() if value else None

class Parroquia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    _nombre = db.Column('nombre', db.String(50), nullable=False)
    municipio_id = db.Column(db.Integer, db.ForeignKey('municipio.id'), nullable=False)
    
    aldeas = db.relationship('AldeaUniversitaria', backref='parroquia', lazy=True)

    @property
    def nombre(self): return self._nombre
    @nombre.setter
    def nombre(self, value): self._nombre = value.upper() if value else None

class AldeaUniversitaria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    _codigo = db.Column('codigo', db.String(10), unique=True, nullable=False)
    _nombre = db.Column('nombre', db.String(100), nullable=False)
    parroquia_id = db.Column(db.Integer, db.ForeignKey('parroquia.id'), nullable=False)
    
    personal = db.relationship('Personal', backref='aldea', lazy=True)
    estudiantes = db.relationship('Estudiante', backref='aldea', lazy=True)

    @property
    def codigo(self): return self._codigo
    @codigo.setter
    def codigo(self, value): self._codigo = value.upper() if value else None
    
    @property
    def nombre(self): return self._nombre
    @nombre.setter
    def nombre(self, value): self._nombre = value.upper() if value else None

    def __repr__(self): return f'<Aldea {self.nombre}>'

# =========================================================
# 3. GESTIÓN DE PERSONAS (Dependientes)
# =========================================================

class Personal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Identificación
    tipo_documento = db.Column(db.String(1), nullable=False) # V o E
    numero_documento = db.Column(db.String(15), unique=True, nullable=False)
    
    _nombre_apellido = db.Column('nombre_apellido', db.String(100), nullable=False)
    correo = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    fecha_nacimiento = db.Column(db.Date)
    _genero = db.Column('genero', db.String(10))
    
    # Relaciones
    cargo_id = db.Column(db.Integer, db.ForeignKey('cargo.id'), nullable=False)
    aldea_id = db.Column(db.Integer, db.ForeignKey('aldea_universitaria.id'), nullable=False)
    
    _tipo_personal = db.Column('tipo_personal', db.String(50))
    cargado_por = db.Column(db.String(50), default='USUARIO')

    @property
    def cedula(self): return f"{self.tipo_documento}-{self.numero_documento}"

    @property
    def nombre_apellido(self): return self._nombre_apellido
    @nombre_apellido.setter
    def nombre_apellido(self, value): self._nombre_apellido = value.upper() if value else None

    @property
    def genero(self): return self._genero
    @genero.setter
    def genero(self, value): self._genero = value.upper() if value else None
    
    @property
    def tipo_personal(self): return self._tipo_personal
    @tipo_personal.setter
    def tipo_personal(self, value): self._tipo_personal = value.upper() if value else None
    
    @property
    def edad(self):
        if self.fecha_nacimiento:
            hoy = datetime.now().date()
            return hoy.year - self.fecha_nacimiento.year - ((hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))
        return None

class Estudiante(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Identificación
    tipo_documento = db.Column(db.String(1), nullable=False)
    numero_documento = db.Column(db.String(15), unique=True, nullable=False)
    
    _nombre_apellido = db.Column('nombre_apellido', db.String(100), nullable=False)
    correo = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    fecha_nacimiento = db.Column(db.Date)
    _genero = db.Column('genero', db.String(10))
    
    # Relaciones Académicas y Geográficas
    carrera_id = db.Column(db.Integer, db.ForeignKey('carrera.id'), nullable=False)
    tramo_id = db.Column(db.Integer, db.ForeignKey('tramo.id'), nullable=False)
    periodo_id = db.Column(db.Integer, db.ForeignKey('periodo_academico.id'), nullable=False)
    aldea_id = db.Column(db.Integer, db.ForeignKey('aldea_universitaria.id'), nullable=False)
    
    cargado_por = db.Column(db.String(50), default='USUARIO')
    
    @property
    def cedula(self): return f"{self.tipo_documento}-{self.numero_documento}"

    @property
    def nombre_apellido(self): return self._nombre_apellido
    @nombre_apellido.setter
    def nombre_apellido(self, value): self._nombre_apellido = value.upper() if value else None

    @property
    def genero(self): return self._genero
    @genero.setter
    def genero(self, value): self._genero = value.upper() if value else None

    @property
    def edad(self):
        if self.fecha_nacimiento:
            hoy = datetime.now().date()
            return hoy.year - self.fecha_nacimiento.year - ((hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))
        return None
    
    @property
    def nombre_tramo(self):
        return self.tramo_obj.nombre if self.tramo_obj else "Sin Asignar"
        
    @property
    def nombre_periodo(self):
        return self.periodo_obj.nombre if self.periodo_obj else "Sin Asignar"

# =========================================================
# 4. SEGURIDAD Y USUARIOS
# =========================================================

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    _nombre_usuario = db.Column('nombre_usuario', db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    _rol = db.Column('rol', db.String(50), nullable=False)
    activo = db.Column(db.Boolean, default=True)

    permisos = db.relationship('PermisoCoordinador', backref='usuario', lazy=True)

    @property
    def nombre_usuario(self): return self._nombre_usuario
    @nombre_usuario.setter
    def nombre_usuario(self, value): self._nombre_usuario = value.upper() if value else None
    
    @property
    def rol(self): return self._rol
    @rol.setter
    def rol(self, value): self._rol = value.upper() if value else None
    
    @property
    def password(self):
        raise AttributeError('La contraseña no es legible.')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self): return f'<Usuario {self.nombre_usuario}>'

class PermisoCoordinador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    municipio_id = db.Column(db.Integer, db.ForeignKey('municipio.id'), nullable=True)
    aldea_id = db.Column(db.Integer, db.ForeignKey('aldea_universitaria.id'), nullable=True)
    
    municipio = db.relationship('Municipio', backref='permisos_municipio', lazy=True)
    aldea = db.relationship('AldeaUniversitaria', backref='permisos_aldea', lazy=True)
    
    def __repr__(self):
        return f'<PermisoCoordinador User:{self.usuario_id}>'