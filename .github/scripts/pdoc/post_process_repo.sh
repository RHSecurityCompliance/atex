#!/bin/bash

set -e

# move any *.md from the repo root to atex/, so it gets processed
# by the code below under the python module root
while IFS= read -r -d '' path; do
  dest="atex/$path"
  if [[ -e $dest ]]; then
    echo "error: '$dest' already exists"
    exit 1
  fi
  # but remove any atex/ prefix in links, since we're moving the files
  # inside the atex/ dir
  sed -r 's/\[(.+)\]\(atex\/(.+)\)/[\1](\2)/g' "$path" > "$dest"
done < <(find . -maxdepth 1 -name '*.md' -print0)

# transform any .md files to .py ones, putting their content into
# a raw docstring
while IFS= read -r -d '' path; do
  file=${path##*/}
  name=${file%.md}
  parent=${path%/*}
  py="$parent/$name.py"
  if [[ -e $py ]]; then
    echo "error: '$py' already exists"
    exit 1
  fi
  echo "transforming '$parent/$file' -> '$py'"
  {
    echo "r'''"
    # [SOME_FOO.md](SOME_FOO.md) --> [SOME_FOO](SOME_FOO)
    # .. and also [some foo](SOME_FOO.md) --> [some foo](SOME_FOO)
    # .. but not [see url](https://external/SOME_FOO.md)
    #
    # additionally, remove backticks in headers (pdoc parser bugs)
    sed -r \
      -e 's/\[(.+).md\]\(([^:\]+).md\)/[\1](\2)/g ; s/\[(.+)\]\(([^:\)]+).md\)/[\1](\2)/g' \
      -e '/^#/s/`//g' \
      "$path"
    echo "'''"
  } > "$py"

  # include the new .py inside __init__.py if it exists in the same
  # directory
  init_py="$parent/__init__.py"
  if [[ -f "$init_py" ]]; then
    echo "including '$name' in '$init_py'"
    printf '\nfrom . import %s  # only for pdoc, not in ATEX\n' "$name" \
      >> "$init_py"
    # if it has __all__, include it in there
    # (don't use += in case it's a non-mutable sequence)
    if grep -q '^__all__' "$init_py"; then
      printf '__all__ = (*__all__, "%s")\n' "$name" \
        >> "$init_py"
    fi
  fi
done < <(find atex -name '*.md' -print0)

# for every __init__.py, look for README.md in the same directory
# and if it exists, include it as a docstring inside __init__.py
# if it itself doesn't have one
while IFS= read -r -d '' path; do
  if grep -E -q "^r?(\"\"\"|''')" "$path"; then
    echo "skipping '$path', has a docstring already"
    continue
  fi

  parent=${path%/*}
  readme="$parent/README.py"
  [[ -e $readme ]] || continue

  # post-process the README docstring, add module-name/ to all relative
  # Markdown links (pdoc treats __init__.py as if it was in the parent)
  module_name=${parent##*/}
  contents=$(sed -r "s/\[(.+)\]\(([^:\]+)\)/[\1](${module_name}\/\2)/g" "$readme")

  # prepend the README to __init__.py
  echo "prepending '$readme' to '$path'"
  {
    printf '%s\n' "$contents"
    cat "$path"
  } > "$path.new"
  mv -f "$path.new" "$path"
done < <(find atex -name '__init__.py' -print0)
