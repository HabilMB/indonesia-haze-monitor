{#- Use dataset names verbatim (staging, marts) instead of dbt's default <target>_<custom> prefixing. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ (custom_schema_name or target.dataset) | trim }}
{%- endmacro %}
