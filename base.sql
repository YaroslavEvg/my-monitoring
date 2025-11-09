CREATE TABLE IF NOT EXISTS public.logins (
    login VARCHAR(255) NOT NULL PRIMARY KEY,
    campus VARCHAR(255),
    level INTEGER,
    avatar_url TEXT
);
