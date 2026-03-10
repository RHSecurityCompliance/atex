#!/bin/bash

# don't add automatic hyperlinks because of bugs like
# `results.json` --> `resultsatex.aggregator.json.json`
render_helpers_py=$(python -c 'import pdoc.render_helpers; print(pdoc.render_helpers.__file__)')
sed '/^    def linkify_repl(/i\ \ \ \ return Markup(code)\n' \
  -i "$render_helpers_py"
