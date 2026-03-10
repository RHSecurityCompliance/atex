#!/bin/bash

templates_dir=$1

mkdir -p "$templates_dir"
cat > "$templates_dir/module.html.jinja2" <<'EOF'
{% extends "default/module.html.jinja2" %}

{% block style %}
{{ super() }}
<style>
    /* Hide all class and module variables that do not have a docstring */
    .variable:not(:has(.docstring)) {
        display: none !important;
    }
</style>
{% endblock %}
EOF
