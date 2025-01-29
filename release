#!/bin/bash

REPO="testpypi"
[ -n "$REPO" ] && REPO="pypi"

version_file="flex_report/_version.py"
increment_type=""
new_version=""

function display_usage {
    echo "Usage: $0 -v <major|minor|patch>"
    exit 1
}

# Parse command line options
while getopts "v: r:" opt; do
    case $opt in
        v)
            increment_type="$OPTARG"
            ;;
        r)
            REPO="$OPTARG"
            ;;
        *)
            display_usage
            ;;
    esac
done

if [ -z "$increment_type" ]; then
    display_usage
fi

current_version=$(grep -oP "__version__ = (\"|')\K[^(\"|')]+" "$version_file")

major=$(echo "$current_version" | cut -d. -f1)
minor=$(echo "$current_version" | cut -d. -f2)
patch=$(echo "$current_version" | cut -d. -f3)

case $increment_type in
    "major")
        major=$((major + 1))
        ;;
    "minor")
        minor=$((minor + 1))
        ;;
    "patch")
        patch=$((patch + 1))
        ;;
    *)
        display_usage
        ;;
esac

# Create the new version string
new_version="$major.$minor.$patch"

sed -i "s/__version__ = \".*\"/__version__ = \"$new_version\"/" "$version_file"

echo "Version updated to: $new_version"


rm -r build dist *.egg*
python setup.py sdist bdist_wheel
[ -n "$REPO" ] && twine upload --repository $REPO dist/* || twine upload dist/*
