-- 1. EXTENSIONES Y SEGURIDAD
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. TABLA DE TENANTS (Instituciones)
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    domain TEXT UNIQUE NOT NULL, -- Ej: 'biourbe.com' o 'itm.edu.co'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. CATÁLOGOS BASE
CREATE TABLE IF NOT EXISTS faculties (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    UNIQUE(tenant_id, name)
);

CREATE TABLE IF NOT EXISTS academic_programs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    faculty_id UUID REFERENCES faculties(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    UNIQUE(tenant_id, name)
);

CREATE TABLE IF NOT EXISTS campuses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    address TEXT,
    UNIQUE(tenant_id, name)
);

-- 4. PERSONAS (Estudiantes y Docentes)
CREATE TABLE IF NOT EXISTS students (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    program_id UUID REFERENCES academic_programs(id),
    external_id TEXT, -- ID del sistema SIGA
    full_name TEXT NOT NULL,
    email TEXT,
    gender TEXT,
    stratum INTEGER, -- Estrato socioeconómico
    birth_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, external_id)
);

CREATE TABLE IF NOT EXISTS teachers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    external_id TEXT,
    full_name TEXT NOT NULL,
    email TEXT,
    department TEXT,
    UNIQUE(tenant_id, external_id)
);

-- 5. ACADÉMICO
CREATE TABLE IF NOT EXISTS subjects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    credits INTEGER DEFAULT 0,
    UNIQUE(tenant_id, code)
);

CREATE TABLE IF NOT EXISTS class_groups (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    subject_id UUID REFERENCES subjects(id) ON DELETE CASCADE,
    teacher_id UUID REFERENCES teachers(id),
    semester TEXT NOT NULL, -- Ej: '2024-1'
    group_code TEXT NOT NULL,
    modality TEXT CHECK (modality IN ('Presencial', 'Teams', 'Híbrido')),
    UNIQUE(tenant_id, subject_id, semester, group_code)
);

CREATE TABLE IF NOT EXISTS group_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    group_id UUID REFERENCES class_groups(id) ON DELETE CASCADE,
    campus_id UUID REFERENCES campuses(id),
    day_of_week INTEGER CHECK (day_of_week BETWEEN 1 AND 7), -- 1: Lunes
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    classroom TEXT
);

-- 6. RENDIMIENTO Y NOTAS
CREATE TABLE IF NOT EXISTS academic_performance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    student_id UUID REFERENCES students(id) ON DELETE CASCADE,
    group_id UUID REFERENCES class_groups(id) ON DELETE CASCADE,
    partial_1 NUMERIC(3,2),
    partial_2 NUMERIC(3,2),
    final_exam NUMERIC(3,2),
    final_grade NUMERIC(3,2),
    is_passing BOOLEAN GENERATED ALWAYS AS (final_grade >= 3.0) STORED,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, student_id, group_id)
);

-- 7. POLÍTICAS RLS (Row Level Security)
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE faculties ENABLE ROW LEVEL SECURITY;
ALTER TABLE academic_programs ENABLE ROW LEVEL SECURITY;
ALTER TABLE campuses ENABLE ROW LEVEL SECURITY;
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE teachers ENABLE ROW LEVEL SECURITY;
ALTER TABLE subjects ENABLE ROW LEVEL SECURITY;
ALTER TABLE class_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE group_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE academic_performance ENABLE ROW LEVEL SECURITY;

-- Ejemplo de política de aislamiento de Tenant
-- Se aplica a todas las tablas para asegurar que una institución no vea datos de otra.
CREATE POLICY tenant_isolation_policy ON academic_performance
    FOR ALL USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);
