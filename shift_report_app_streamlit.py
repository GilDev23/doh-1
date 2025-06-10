import streamlit as st
import duckdb
from datetime import datetime, date, time
import pandas as pd

# הגדרת הדף
st.set_page_config(page_title="דיווח משמרת", layout="centered", page_icon="📝")

# התחברות לבסיס הנתונים
@st.cache_resource
def init_database():
    try:
        con = duckdb.connect("reports.db")
        con.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            report_type TEXT,
            personal_id TEXT,
            reporter_name TEXT,
            unit_commander TEXT,
            work_location TEXT,
            replacing_who TEXT,
            replacement_person TEXT,
            reports_count INTEGER,
            special_notes TEXT,
            timestamp TEXT,
            start_date TEXT,
            start_time TEXT,
            end_date TEXT,
            end_time TEXT
        )
        """)
        return con
    except Exception as e:
        st.error(f"שגיאה בהתחברות למסד הנתונים: {e}")
        return None

# בדיקה אם יש חיבור למסד נתונים
con = init_database()

if con is None:
    st.stop()

# תפריט ניווט
st.sidebar.title("🧭 ניווט")
page = st.sidebar.selectbox("בחר עמוד:", ["""דו"ח 1""", "ADMIN"])

personal_data = {
    "6417388": "אסף גבור",
    "8284468": "חיה סגל",
    "5929261": "צאלח חיר"
}

# עמוד דיווח שעות עם הגנת קוד
if page == "ADMIN":
    st.title("⏰ דף מפקד")
    st.markdown("---")
    
    # בדיקת קוד גישה
    if 'access_granted' not in st.session_state:
        st.session_state.access_granted = False
    
    if not st.session_state.access_granted:
        st.subheader("🔐 הכנס קוד גישה")
        access_code = st.text_input("קוד גישה:", type="password")
        
        if st.button("אמת קוד"):
            if access_code == "365365":
                st.session_state.access_granted = True
                st.success("✅ קוד נכון! כעת יש לך גישה לדיווח השעות")
                st.rerun()
            else:
                st.error("❌ קוד שגוי!")
        st.stop()
    
    # הצגת דיווח שעות
    st.subheader("📊 סיכום שעות עבודה השבוע")
    
    try:
        # חישוב תאריכי השבוע הנוכחי (ראשון עד ראשון)
        today = date.today()
        days_since_sunday = (today.weekday() + 1) % 7
        week_start = today - pd.Timedelta(days=days_since_sunday)
        week_end = week_start + pd.Timedelta(days=6)
        
        st.info(f"השבוע: {week_start.strftime('%d/%m/%Y')} - {week_end.strftime('%d/%m/%Y')}")
        
        # שאילתה לחישוב שעות עבודה - מפושטת
        hours_query = """
        WITH entry_exits AS (
            SELECT 
                e.personal_id,
                e.reporter_name,
                e.start_date,
                e.start_time,
                e.timestamp as entry_time,
                (SELECT x.end_date FROM reports x 
                 WHERE x.personal_id = e.personal_id 
                 AND x.report_type = 'exit' 
                 AND x.timestamp > e.timestamp 
                 ORDER BY x.timestamp LIMIT 1) as end_date,
                (SELECT x.end_time FROM reports x 
                 WHERE x.personal_id = e.personal_id 
                 AND x.report_type = 'exit' 
                 AND x.timestamp > e.timestamp 
                 ORDER BY x.timestamp LIMIT 1) as end_time
            FROM reports e
            WHERE e.report_type = 'entry'
            AND DATE(e.start_date) >= ? 
            AND DATE(e.start_date) <= ?
        ),
        calculated_hours AS (
            SELECT 
                personal_id,
                reporter_name,
                start_date,
                start_time,
                end_date,
                end_time,
                CASE 
                    WHEN start_time IS NOT NULL AND end_time IS NOT NULL 
                    AND start_date IS NOT NULL AND end_date IS NOT NULL THEN
                        CASE 
                            WHEN start_date = end_date THEN
                                (EXTRACT('hour' FROM CAST(end_time AS TIME)) * 60 + EXTRACT('minute' FROM CAST(end_time AS TIME))) -
                                (EXTRACT('hour' FROM CAST(start_time AS TIME)) * 60 + EXTRACT('minute' FROM CAST(start_time AS TIME)))
                            ELSE
                                -- חישוב עבור משמרות שעוברות חצות
                                (24 * 60) - (EXTRACT('hour' FROM CAST(start_time AS TIME)) * 60 + EXTRACT('minute' FROM CAST(start_time AS TIME))) +
                                (EXTRACT('hour' FROM CAST(end_time AS TIME)) * 60 + EXTRACT('minute' FROM CAST(end_time AS TIME)))
                        END / 60.0
                    ELSE NULL
                END as hours_worked
            FROM entry_exits
        )
        SELECT 
            personal_id,
            reporter_name,
            COUNT(*) as total_shifts,
            COUNT(*) FILTER (WHERE hours_worked IS NOT NULL) as completed_shifts,
            ROUND(SUM(COALESCE(hours_worked, 0)), 2) as total_hours,
            ROUND(AVG(hours_worked), 2) as avg_hours_per_shift,
            MIN(start_date) as first_shift_date,
            MAX(COALESCE(end_date, start_date)) as last_shift_date
        FROM calculated_hours
        GROUP BY personal_id, reporter_name
        ORDER BY total_hours DESC
        """
        
        results = con.execute(hours_query, [week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d')]).fetchall()
        
        if results:
            # יצירת DataFrame להצגה
            df = pd.DataFrame(results, columns=[
                'מס אישי', 'שם', 'סה״כ משמרות', 'משמרות שהושלמו', 
                'סה״כ שעות', 'ממוצע שעות למשמרת', 'תאריך ראשון', 'תאריך אחרון'
            ])
            
            # הצגת סיכום כללי
            total_hours_all = df['סה״כ שעות'].sum()
            total_shifts_all = df['סה״כ משמרות'].sum()
            active_employees = len(df)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("סה״כ שעות השבוע", f"{total_hours_all:.1f}")
            with col2:
                st.metric("סה״כ משמרות", total_shifts_all)
            with col3:
                st.metric("עובדים פעילים", active_employees)
            
            # הצגת הטבלה
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )
            
            # גרף שעות עבודה
            if len(df) > 0:
                st.subheader("📈 גרף שעות עבודה")
                chart_data = df.set_index('שם')['סה״כ שעות']
                st.bar_chart(chart_data)
            
            # פירוט יומי לכל עובד
            if st.checkbox("🔍 הצג פירוט יומי"):
                selected_employee = st.selectbox(
                    "בחר עובד:",
                    options=df['מס אישי'].tolist(),
                    format_func=lambda x: f"{df[df['מס אישי']==x]['שם'].iloc[0]} ({x})"
                )
                
                if selected_employee:
                    # שאילתה לפירוט יומי - מפושטת
                    daily_query = """
                    WITH daily_shifts AS (
                        SELECT 
                            e.start_date,
                            e.start_time,
                            (SELECT x.end_date FROM reports x 
                             WHERE x.personal_id = e.personal_id 
                             AND x.report_type = 'exit' 
                             AND x.timestamp > e.timestamp 
                             ORDER BY x.timestamp LIMIT 1) as end_date,
                            (SELECT x.end_time FROM reports x 
                             WHERE x.personal_id = e.personal_id 
                             AND x.report_type = 'exit' 
                             AND x.timestamp > e.timestamp 
                             ORDER BY x.timestamp LIMIT 1) as end_time
                        FROM reports e
                        WHERE e.report_type = 'entry'
                        AND e.personal_id = ?
                        AND DATE(e.start_date) >= ? 
                        AND DATE(e.start_date) <= ?
                    )
                    SELECT 
                        start_date,
                        start_time,
                        end_date,
                        end_time,
                        CASE 
                            WHEN start_time IS NOT NULL AND end_time IS NOT NULL 
                            AND start_date IS NOT NULL AND end_date IS NOT NULL THEN
                                ROUND(
                                    CASE 
                                        WHEN start_date = end_date THEN
                                            ((EXTRACT('hour' FROM CAST(end_time AS TIME)) * 60 + EXTRACT('minute' FROM CAST(end_time AS TIME))) -
                                            (EXTRACT('hour' FROM CAST(start_time AS TIME)) * 60 + EXTRACT('minute' FROM CAST(start_time AS TIME)))) / 60.0
                                        ELSE
                                            (((24 * 60) - (EXTRACT('hour' FROM CAST(start_time AS TIME)) * 60 + EXTRACT('minute' FROM CAST(start_time AS TIME))) +
                                            (EXTRACT('hour' FROM CAST(end_time AS TIME)) * 60 + EXTRACT('minute' FROM CAST(end_time AS TIME)))) / 60.0)
                                    END, 2
                                )
                            ELSE NULL
                        END as hours_worked
                    FROM daily_shifts
                    ORDER BY start_date, start_time
                    """
                    
                    daily_results = con.execute(daily_query, [
                        selected_employee, 
                        week_start.strftime('%Y-%m-%d'), 
                        week_end.strftime('%Y-%m-%d')
                    ]).fetchall()
                    
                    if daily_results:
                        daily_df = pd.DataFrame(daily_results, columns=[
                            'תאריך כניסה', 'שעת כניסה', 'תאריך יציאה', 'שעת יציאה', 'שעות עבודה'
                        ])
                        st.dataframe(daily_df, use_container_width=True, hide_index=True)
                    else:
                        st.info("אין נתונים לעובד זה השבוע")
        else:
            st.info("אין נתונים לשבוע הנוכחי")
            
    except Exception as e:
        st.error(f"שגיאה בטעינת נתוני השעות: {str(e)}")
    
    # כפתור יציאה
    if st.button("🚪 יציאה מדיווח שעות"):
        st.session_state.access_granted = False
        st.rerun()

# עמוד דיווח משמרת הרגיל
else:
    # כותרת ראשית
    st.title("""📝 דו"ח 1""")
    st.markdown("---")

    # בחירת סוג דיווח
    report_type = st.selectbox(
        "בחר סוג דיווח:", 
        ["entry", "exit"], 
        format_func=lambda x: "🟢 כניסה למשמרת" if x == "entry" else "🔴 יציאה ממשמרת"
    )

    # טופס הדיווח
    with st.form("report_form", clear_on_submit=True):
        st.subheader(f"{'כניסה למשמרת' if report_type == 'entry' else 'יציאה ממשמרת'}")
        
        # שדות משותפים
        col1, col2 = st.columns(2)
        
        with col1:
            personal_id = st.text_input("מספר אישי (מ.א.) *", placeholder="הכנס מספר אישי")
            if personal_id in personal_data:
                reporter_name = personal_data[personal_id]
            else:
                reporter_name = "מספר לא נמצא"


            reporter_name = (f"{reporter_name}")
        
        with col2:
            unit_commander = st.selectbox("מפקד החוליה *", ["ויסאם אסד" , "יובל שטפל" , "ירדן קרן", "דניאל הנו" , "נזיה הנו" , "אסף גבור" , "נתי שיינפלד","כנרת המבורגר"])
        
        # שדות ספציפיים לסוג דיווח
        if report_type == "entry":
            col3, col4 = st.columns(2)
            
            with col3:
                work_location = st.selectbox("מיקום עבודה:", ["גלילות", "משגב", "בית", "אחר"])
                if work_location == "אחר":
                    work_location = st.text_input("פרט מיקום:", placeholder="הכנס מיקום")
            
            with col4:
                replacing_who = st.selectbox(": את מי אתה מחליף",["אסף גבור","חיה סגל","צאלח חיר"])
            
            # תאריך ושעה נוכחיים (לא ניתנים לשינוי)
            current_date = date.today()
            current_time = datetime.now().time().replace(microsecond=0)
            
            col5, col6 = st.columns(2)
            with col5:
                st.text_input("תאריך תחילת משמרת:", value=current_date.strftime('%d/%m/%Y'), disabled=True)
                start_date = current_date
            with col6:
                st.text_input("שעת תחילת משמרת:", value=current_time.strftime('%H:%M'), disabled=True)
                start_time = current_time

            # משתנים ריקים ליציאה
            replacement_person = None
            reports_count = None
            end_date = None
            end_time = None
            special_notes = None

        else:  # exit
            col3, col4 = st.columns(2)
            
            with col3:
                replacement_person = st.selectbox("מי מחליף אותך:", ["אסף גבור","חיה סגל","צאלח חיר"])
            
            with col4:
                reports_count = st.number_input("מספר דיווחים שהעלית במשמרת *:", min_value=0, step=1, value=0)
            
            # תאריך ושעה נוכחיים (לא ניתנים לשינוי)
            current_date = date.today()
            current_time = datetime.now().time().replace(microsecond=0)
            
            col5, col6 = st.columns(2)
            with col5:
                st.text_input("תאריך סיום משמרת:", value=current_date.strftime('%d/%m/%Y'), disabled=True)
                end_date = current_date
            with col6:
                st.text_input("שעת סיום משמרת:", value=current_time.strftime('%H:%M'), disabled=True)
                end_time = current_time
            
            special_notes = st.text_area("הערות מיוחדות:", placeholder="הערות או דברים חשובים...")

            # משתנים ריקים לכניסה
            work_location = None
            replacing_who = None
            start_date = None
            start_time = None

        # כפתור שליחה
        submitted = st.form_submit_button("📤 שלח דיווח", type="primary")

        if submitted:
            # בדיקת שדות חובה
            required_fields_missing = []
            if not personal_id:
                required_fields_missing.append("מספר אישי")
            if not unit_commander:
                required_fields_missing.append("מפקד החוליה")
            if not reporter_name:
                required_fields_missing.append("שם הדווח")
            if report_type == "exit" and reports_count is None:
                required_fields_missing.append("מספר דיווחים")
                
            if required_fields_missing:
                st.error(f"❌ נא למלא את השדות הנדרשים: {', '.join(required_fields_missing)}")
            else:
                try:
                    timestamp = datetime.now().isoformat()
                    
                    con.execute("""
                        INSERT INTO reports (
                            report_type, personal_id, reporter_name, unit_commander,
                            work_location, replacing_who, replacement_person,
                            reports_count, special_notes, timestamp,
                            start_date, start_time, end_date, end_time
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        report_type, 
                        personal_id,
                        reporter_name,
                        unit_commander,
                        work_location,
                        replacing_who,
                        replacement_person,
                        reports_count,
                        special_notes,
                        timestamp,
                        str(start_date) if start_date else None,
                        str(start_time) if start_time else None,
                        str(end_date) if end_date else None,
                        str(end_time) if end_time else None
                    ))
                    
                    st.success("✅ הדיווח נשלח בהצלחה!")
                    st.balloons()
                    
                except Exception as e:
                    st.error(f"❌ שגיאה בשמירת הדיווח: {str(e)}")

    # קו הפרדה
    st.markdown("---")

    # סטטיסטיקות - עדכון להתמקד בדיווחים שהועלו
    # st.subheader("📊 סטטיסטיקות")

    # try:
    #     # שאילתת סטטיסטיקות מעודכנת עם דגש על דיווחים שהועלו
    #     stats_query = """
    #         WITH shift_data AS (
    #             SELECT 
    #                 *,
    #                 CASE 
    #                     WHEN report_type = 'entry' AND start_time IS NOT NULL THEN
    #                         CASE 
    #                             WHEN start_time >= '07:00:00' AND start_time < '15:00:00' THEN 'בוקר (07:00-15:00)'
    #                             WHEN start_time >= '15:00:00' AND start_time < '23:00:00' THEN 'צהריים (15:00-23:00)'
    #                             ELSE 'לילה (23:00-07:00)'
    #                         END
    #                     WHEN report_type = 'exit' AND end_time IS NOT NULL THEN
    #                         CASE 
    #                             WHEN end_time >= '07:00:00' AND end_time < '15:00:00' THEN 'בוקר (07:00-15:00)'
    #                             WHEN end_time >= '15:00:00' AND end_time < '23:00:00' THEN 'צהריים (15:00-23:00)'
    #                             ELSE 'לילה (23:00-07:00)'
    #                         END
    #                     ELSE 'לא צוין'
    #                 END as shift_period
    #             FROM reports
    #         )
    #         SELECT
    #             COUNT(*) AS total_reports,
    #             COUNT(*) FILTER (WHERE DATE(timestamp) = CURRENT_DATE) AS today_reports,
    #             COUNT(*) FILTER (WHERE report_type = 'entry') AS total_entries,
    #             COUNT(*) FILTER (WHERE report_type = 'exit') AS total_exits,
    #             COUNT(DISTINCT DATE(timestamp)) AS total_days,
    #             -- סה"כ דיווחים שהועלו (רק מיציאות)
    #             SUM(CASE WHEN report_type = 'exit' AND reports_count IS NOT NULL THEN reports_count ELSE 0 END) as total_uploaded_reports,
    #             -- ממוצע דיווחים שהועלו למשמרת
    #             CASE 
    #                 WHEN COUNT(*) FILTER (WHERE report_type = 'exit' AND reports_count IS NOT NULL) > 0 
    #                 THEN ROUND(
    #                     CAST(SUM(CASE WHEN report_type = 'exit' AND reports_count IS NOT NULL THEN reports_count ELSE 0 END) AS FLOAT) / 
    #                     CAST(COUNT(*) FILTER (WHERE report_type = 'exit' AND reports_count IS NOT NULL) AS FLOAT), 2
    #                 )
    #                 ELSE 0 
    #             END as avg_reports_per_exit,
    #             -- סטטיסטיקות לפי משמרות
    #             COUNT(*) FILTER (WHERE shift_period = 'בוקר (07:00-15:00)') AS morning_shifts,
    #             COUNT(*) FILTER (WHERE shift_period = 'צהריים (15:00-23:00)') AS afternoon_shifts,
    #             COUNT(*) FILTER (WHERE shift_period = 'לילה (23:00-07:00)') AS night_shifts,
    #             -- ממוצע דיווחים שהועלו לפי סוג משמרת
    #             AVG(reports_count) FILTER (WHERE shift_period = 'בוקר (07:00-15:00)' AND reports_count IS NOT NULL) AS avg_morning_reports,
    #             AVG(reports_count) FILTER (WHERE shift_period = 'צהריים (15:00-23:00)' AND reports_count IS NOT NULL) AS avg_afternoon_reports,
    #             AVG(reports_count) FILTER (WHERE shift_period = 'לילה (23:00-07:00)' AND reports_count IS NOT NULL) AS avg_night_reports
    #         FROM shift_data
    #     """
    #     results = con.execute(stats_query).fetchone()

    #     # הצגת מטריקות עיקריות
    #     col1, col2, col3, col4 = st.columns(4)
        
    #     with col1:
    #         st.metric("סה\"כ דיווחי מערכת", results[0] if results[0] else 0)
        
    #     with col2:
    #         st.metric("דיווחי מערכת היום", results[1] if results[1] else 0)
        
    #     with col3:
    #         active_shifts = max(0, (results[2] if results[2] else 0) - (results[3] if results[3] else 0))
    #         st.metric("משמרות פעילות", active_shifts)
        
    #     with col4:
    #         st.metric("סה\"כ דיווחים שהועלו", results[5] if results[5] else 0)

    #     # סטטיסטיקות מפורטות
    #     st.markdown("### 📈 סטטיסטיקות מפורטות")
        
    #     col5, col6 = st.columns(2)
        
    #     with col5:
    #         st.info(f"**כניסות למשמרת:** {results[2] if results[2] else 0}")
    #         st.info(f"**יציאות ממשמרת:** {results[3] if results[3] else 0}")
    #         st.info(f"**ימי פעילות:** {results[4] if results[4] else 0}")
        
    #     with col6:
    #         avg_reports_per_exit = results[6] if results[6] else 0
    #         st.info(f"**ממוצע דיווחים שהועלו למשמרת:** {avg_reports_per_exit}")
    #         completed_shifts = results[3] if results[3] else 0
    #         st.info(f"**משמרות שהושלמו:** {completed_shifts}")

    #     # סטטיסטיקות לפי משמרות
    #     st.markdown("### 🕐 התפלגות לפי משמרות")
        
    #     shift_col1, shift_col2, shift_col3 = st.columns(3)
        
    #     with shift_col1:
    #         st.markdown("**🌅 משמרת בוקר (07:00-15:00)**")
    #         morning_count = results[7] if results[7] else 0
    #         morning_avg = round(results[10], 1) if results[10] else 0
    #         st.write(f"דיווחי מערכת: {morning_count}")
    #         st.write(f"ממוצע דיווחים שהועלו: {morning_avg}")
        
    #     with shift_col2:
    #         st.markdown("**☀️ משמרת צהריים (15:00-23:00)**")
    #         afternoon_count = results[8] if results[8] else 0
    #         afternoon_avg = round(results[11], 1) if results[11] else 0
    #         st.write(f"דיווחי מערכת: {afternoon_count}")
    #         st.write(f"ממוצע דיווחים שהועלו: {afternoon_avg}")
        
    #     with shift_col3:
    #         st.markdown("**🌙 משמרת לילה (23:00-07:00)**")
    #         night_count = results[9] if results[9] else 0
    #         night_avg = round(results[12], 1) if results[12] else 0
    #         st.write(f"דיווחי מערכת: {night_count}")
    #         st.write(f"ממוצע דיווחים שהועלו: {night_avg}")

    #     # גרף התפלגות משמרות (אם יש נתונים)
    #     if any([results[7], results[8], results[9]]):
    #         st.markdown("### 📊 גרף התפלגות משמרות")
            
    #         shift_data = {
    #             'משמרת': ['בוקר', 'צהריים', 'לילה'],
    #             'כמות דיווחי מערכת': [results[7] or 0, results[8] or 0, results[9] or 0]
    #         }
            
    #         df = pd.DataFrame(shift_data)
    #         st.bar_chart(df.set_index('משמרת'))

    # except Exception as e:
    #     st.error(f"שגיאה בטעינת הסטטיסטיקות: {str(e)}")

    # # דיווחים אחרונים והערות
    # col_left, col_right = st.columns(2)

    # with col_left:
    #     if st.checkbox("🔍 הצג דיווחים אחרונים"):
    #         try:
    #             recent_reports = con.execute("""
    #                 SELECT 
    #                     report_type,
    #                     personal_id,
    #                     reporter_name,
    #                     unit_commander,
    #                     reports_count,
    #                     CASE 
    #                         WHEN report_type = 'entry' THEN start_date || ' ' || start_time
    #                         ELSE end_date || ' ' || end_time
    #                     END as datetime,
    #                     timestamp
    #                 FROM reports 
    #                 ORDER BY timestamp DESC 
    #                 LIMIT 10
    #             """).fetchall()
                
    #             if recent_reports:
    #                 st.subheader("📋 דיווחים אחרונים")
    #                 for i, report in enumerate(recent_reports, 1):
    #                     report_type_hebrew = "🟢 כניסה" if report[0] == "entry" else "🔴 יציאה"
    #                     reports_info = f" ({report[4]} דיווחים)" if report[0] == "exit" and report[4] is not None else ""
    #                     st.write(f"{i}. **{report_type_hebrew}** - {report[2]} (מ.א. {report[1]}) - מפקד: {report[3]}{reports_info} - {report[5]}")
    #             else:
    #                 st.info("אין דיווחים קיימים במערכת")
                    
    #         except Exception as e:
    #             st.error(f"שגיאה בטעינת הדיווחים: {str(e)}")

    # with col_right:
    #     if st.checkbox("💬 הצג הערות מיוחדות"):
    #         try:
    #             notes_query = """
    #                 SELECT 
    #                     reporter_name,
    #                     personal_id,
    #                     special_notes,
    #                     reports_count,
    #                     CASE 
    #                         WHEN report_type = 'entry' THEN start_date
    #                         ELSE end_date
    #                     END as report_date,
    #                     report_type
    #                 FROM reports 
    #                 WHERE special_notes IS NOT NULL 
    #                 AND special_notes != ''
    #                 ORDER BY timestamp DESC 
    #                 LIMIT 15
    #             """
    #             notes_reports = con.execute(notes_query).fetchall()
                
    #             if notes_reports:
    #                 st.subheader("📝 הערות מיוחדות")
    #                 for note in notes_reports:
    #                     report_type_hebrew = "כניסה" if note[5] == "entry" else "יציאה"
    #                     reports_info = f" - {note[3]} דיווחים" if note[5] == "exit" and note[3] is not None else ""
    #                     with st.expander(f"{note[0]} ({report_type_hebrew}) - {note[4]}{reports_info}"):
    #                         st.write(f"**מ.א.:** {note[1]}")
    #                         st.write(f"**הערה:** {note[2]}")
    #             else:
    #                 st.info("אין הערות מיוחדות במערכת")
                    
    #         except Exception as e:
    #             st.error(f"שגיאה בטעינת ההערות: {str(e)}")

    # מידע נוסף
    with st.expander("ℹ️ הוראות שימוש"):
        st.markdown("""
        **איך להשתמש במערכת:**
        
        1. **בחר סוג דיווח** - כניסה או יציאה ממשמרת
        2. **מלא את הפרטים הנדרשים** - שדות עם כוכבית (*) הם חובה
        3. **ביציאה - ציין כמות הדיווחים שהעלית** - זה נתון חשוב למעקב
        4. **התאריך והשעה נקבעים אוטומטית** - לא ניתן לשינוי
        5. **לחץ על 'שלח דיווח'** לשמירה במערכת
        
        **הערות חשובות:**
        - ✅ וודא שמספר האישי נכון
        - ✅ במשמרת יציאה - חובה לציין כמות הדיווחים שהעלית
        - ✅ התאריך והשעה נקבעים אוטומטית למועד הדיווח
        - ✅ כתוב הערות מיוחדות במידת הצורך
        - ✅ המערכת תשמור את הדיווח באופן אוטומטי
        - 🔐 לגישה לדיווח שעות השתמש בתפריט הצד
        """)

# פוטר
st.markdown("---")
st.markdown("*מערכת דיווח משמרות - גרסה 2.0*")
