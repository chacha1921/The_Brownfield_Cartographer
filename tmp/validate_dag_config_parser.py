from analyzers.dag_config_parser import parse_airflow_dag_file, parse_dbt_schema_file

print(parse_airflow_dag_file('tmp/airflow_sample_dag.py'))
print(parse_dbt_schema_file('tmp/dbt_schema_sample.yml'))
