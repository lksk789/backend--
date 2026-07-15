-- 데이터베이스 스키마 명세서 (ERD) 기반 초기화 스크립트
-- PostgreSQL 권장

-- 1. users (유저 정보)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. user_tastes (유저 취향 데이터)
CREATE TABLE IF NOT EXISTS user_tastes (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tag_name VARCHAR(255) NOT NULL,
    score INT DEFAULT 0
);

-- 3. mangas (만화 마스터 데이터)
CREATE TABLE IF NOT EXISTS mangas (
    id VARCHAR(255) PRIMARY KEY,
    title VARCHAR(255) UNIQUE NOT NULL,
    genre VARCHAR(255),
    author VARCHAR(255),
    release_year INT,
    image_url TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. manga_stats (글로벌 통합 랭킹)
CREATE TABLE IF NOT EXISTS manga_stats (
    manga_id VARCHAR(255) PRIMARY KEY REFERENCES mangas(id) ON DELETE CASCADE,
    balance_picks INT DEFAULT 0,
    world_cup_wins INT DEFAULT 0,
    total_score INT DEFAULT 0
);

-- 5. ai_curation_cache (동적 큐레이션 캐싱)
CREATE TABLE IF NOT EXISTS ai_curation_cache (
    id SERIAL PRIMARY KEY,
    theme_keyword VARCHAR(255) UNIQUE NOT NULL,
    manga_ids JSONB NOT NULL,
    ai_comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 추가 (조회 성능 최적화)
CREATE INDEX IF NOT EXISTS idx_user_tastes_user_id ON user_tastes(user_id);
CREATE INDEX IF NOT EXISTS idx_manga_stats_total_score ON manga_stats(total_score DESC);
CREATE INDEX IF NOT EXISTS idx_ai_curation_cache_theme ON ai_curation_cache(theme_keyword);
