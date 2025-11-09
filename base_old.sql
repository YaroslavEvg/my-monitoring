SELECT
    *
FROM
    logins;

SELECT
    COUNT(*)
FROM
    logins;

SELECT DISTINCT
    campus
FROM
    logins;

SELECT
    campus,
    COUNT(login) AS login_count
FROM
    logins
GROUP BY
    campus;

SELECT
    *
FROM
    logins
ORDER BY
    level DESC;

SELECT
    avatar_url,
    MAX(login) AS login,
    MAX(level) AS level,
    MAX(campus) AS campus
FROM
    logins
GROUP BY
    avatar_url
ORDER BY
    avatar_url DESC;

SELECT
    *
FROM
    logins
WHERE
    campus = '21 Moscow';

CREATE TABLE IF NOT EXISTS logins(
    id serial PRIMARY KEY,
    login VARCHAR(255) UNIQUE NOT NULL
);

ALTER TABLE logins
    ADD COLUMN IF NOT EXISTS coreprogram BOOL DEFAULT FALSE;

ALTER TABLE courses
    ADD COLUMN IF NOT EXISTS local_course_id int;

ADD COLUMN IF NOT EXISTS dismiss BOOL,
ADD COLUMN IF NOT EXISTS campus VARCHAR(255),
ADD COLUMN IF NOT EXISTS level INTEGER,
ADD COLUMN IF NOT EXISTS campus VARCHAR(255),
ADD COLUMN IF NOT EXISTS schoolId VARCHAR(255),
ADD COLUMN IF NOT EXISTS isActive BOOL,
ADD COLUMN IF NOT EXISTS isGraduate BOOL,
ADD COLUMN IF NOT EXISTS studentId VARCHAR(255),
ADD COLUMN IF NOT EXISTS userId VARCHAR(255),
ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(255);

ALTER TABLE logins
    ADD COLUMN IF NOT EXISTS cred_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE logins
    ADD COLUMN IF NOT EXISTS pools_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE user_sourses
    ADD COLUMN IF NOT EXISTS projects_updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS courses(
    id int,
    name varchar(255) NOT NULL,
    displayed_course_status varchar(50),
    execution_type varchar(50),
    final_percentage int,
    experience int,
    course_type varchar(50),
    local_course_id int UNIQUE,
    goal_status varchar(50)
);

CREATE TABLE IF NOT EXISTS courses_projects(
    id serial PRIMARY KEY,
    status varchar(255),
    goal_id int UNIQUE,
    goal_name varchar(255),
    execution_type varchar(50)
);

CREATE TABLE IF NOT EXISTS projects(
    id serial PRIMARY KEY,
    goal_id int UNIQUE,
    name varchar(255) NOT NULL,
    displayed_course_status varchar(50),
    execution_type varchar(50),
    final_percentage int,
    experience int,
    course_type varchar(50),
    local_course_id int,
    goal_status varchar(50)
);

CREATE TABLE IF NOT EXISTS projects_all(
    id serial PRIMARY KEY,
    goal_id int,
    project_name varchar(255),
    project_status varchar(255),
    execution_type varchar(50),
    FOREIGN KEY (goal_id) REFERENCES projects(goal_id),
    FOREIGN KEY (goal_id) REFERENCES courses_projects(goal_id)
);
