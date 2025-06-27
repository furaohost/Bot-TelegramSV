-- === Tabelas extras: Comunidades, Membros, Ofertas, Conteúdos, Chamadas de vídeo ===

CREATE TABLE IF NOT EXISTS comunidades (
    id SERIAL PRIMARY KEY,
    nome TEXT UNIQUE NOT NULL,
    descricao TEXT,
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS membros (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    comunidade_id INT REFERENCES comunidades(id),
    nivel TEXT DEFAULT 'free'        -- free | vip | externo
);

CREATE TABLE IF NOT EXISTS ofertas (
    id SERIAL PRIMARY KEY,
    titulo TEXT NOT NULL,
    descricao TEXT,
    link TEXT,
    data_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_fim TIMESTAMP,
    comunidade_id INT REFERENCES comunidades(id)
);

CREATE TABLE IF NOT EXISTS conteudos (
    id SERIAL PRIMARY KEY,
    titulo TEXT,
    arquivo_id TEXT,                 -- file_id do Telegram ou URL
    tipo TEXT,                       -- text | photo | video
    comunidade_id INT REFERENCES comunidades(id),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chamadas_video (
    id SERIAL PRIMARY KEY,
    titulo TEXT,
    link TEXT,
    horario TIMESTAMP,
    comunidade_id INT REFERENCES comunidades(id)
);
