from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

extract = BashOperator(task_id="extract_orders", bash_command="python extract.py")
transform = PythonOperator(task_id="transform_orders", python_callable=run_transform)
load = BashOperator(task_id="load_orders", bash_command="python load.py")

extract >> transform >> load
