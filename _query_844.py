import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
django.setup()

from django.db import connection

cursor = connection.cursor()

# Find session tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%session%'")
print("Session tables:", [r[0] for r in cursor.fetchall()])

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%class%'")
print("Class tables:", [r[0] for r in cursor.fetchall()])

# 8-4-4 grade IDs: 15-26
grade_ids = list(range(15, 27))
ph = ','.join(str(g) for g in grade_ids)

# Try class_sessions table
for tbl in ['class_sessions', 'academics_classsession', 'academics_class_sessions', 'lesson_sessions_classsession']:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {tbl} WHERE grade_id IN ({ph})")
        count = cursor.fetchone()[0]
        print(f"\n{tbl}: {count} records with 8-4-4 grades")
        if count > 0:
            cursor.execute(f"PRAGMA table_info({tbl})")
            cols = [r[1] for r in cursor.fetchall()]
            print(f"  Columns: {cols}")
            cursor.execute(f"SELECT * FROM {tbl} WHERE grade_id IN ({ph}) LIMIT 10")
            for row in cursor.fetchall():
                print(f"  {dict(zip(cols, row))}")
    except Exception as e:
        print(f"{tbl}: {e}")

# Check StudentSessionEnrollment
for tbl in ['student_session_enrollments', 'academics_studentsessionenrollment']:
    try:
        cursor.execute(f"PRAGMA table_info({tbl})")
        cols = [r[1] for r in cursor.fetchall()]
        print(f"\n{tbl} columns: {cols}")
        # Need to join to get 8-4-4 sessions
        # First find the class session table name
        cs_tbl = None
        for t in ['class_sessions', 'lesson_sessions_classsession']:
            try:
                cursor.execute(f"SELECT 1 FROM {t} LIMIT 1")
                cs_tbl = t
                break
            except:
                pass
        if cs_tbl and 'class_session_id' in cols:
            cursor.execute(f"""
                SELECT COUNT(*) FROM {tbl} e
                JOIN {cs_tbl} cs ON e.class_session_id = cs.id
                WHERE cs.grade_id IN ({ph})
            """)
            cnt = cursor.fetchone()[0]
            print(f"  Enrollments in 8-4-4 sessions: {cnt}")
            if cnt > 0:
                cursor.execute(f"""
                    SELECT e.id, e.student_id, e.class_session_id, cs.grade_id
                    FROM {tbl} e
                    JOIN {cs_tbl} cs ON e.class_session_id = cs.id
                    WHERE cs.grade_id IN ({ph}) LIMIT 10
                """)
                for row in cursor.fetchall():
                    print(f"  enrollment_id={row[0]}, student_id={row[1]}, class_session_id={row[2]}, grade_id={row[3]}")
    except Exception as e:
        print(f"{tbl}: {e}")

# Also check Intake records
print("\n--- INTAKE RECORDS ---")
cursor.execute("SELECT * FROM intakes")
cols_cursor = cursor.description
if cols_cursor:
    cols = [c[0] for c in cols_cursor]
    print(f"Columns: {cols}")
    for row in cursor.fetchall():
        print(dict(zip(cols, row)))
