from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator

extract = PythonOperator(task_id="extract", python_callable=lambda: None)
transform = BashOperator(task_id="transform", bash_command="echo transform")
load = PythonOperator(task_id="load", python_callable=lambda: None)
notify = BashOperator(task_id="notify", bash_command="echo notify")

extract >> transform >> load
[load, transform] >> notify
