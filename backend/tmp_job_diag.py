import sqlite3 
c=sqlite3.connect('backend/arxiviz.db') 
cur=c.cursor() 
jid='job_b8469fbfa3f0' 
row=cur.execute('select id,paper_id,status,progress,sections_completed,sections_total,current_step,error,created_at,completed_at from processing_jobs where id=?',(jid,)).fetchone() 
print('JOB',row) 
pid=row[1] if row else None 
if pid: print('VIZ',cur.execute('select id,status,substr(error,1,200),video_url from visualizations where paper_id=? order by id',(pid,)).fetchall()) 
