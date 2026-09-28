#!/bin/zsh
# build_resume.sh <variant|path/to/file.tex> [OutName]
# 编译 → 检查页数 / 字体丢字 / 未定义命令 → 复制到 config.json 的 resume_out（{suffix} 处填 _Suffix）
# 简历仓库、输出文件名、变体表都在本机数据目录的 config.json 里
set -e
HERE=${0:A:h}
eval "$(python3 - "$HERE" <<'PY'
import sys, shlex
sys.path.insert(0, sys.argv[1])
from _config import config, path
c = config()
print(f"R={shlex.quote(str(path('resume_repo')))}")
print(f"OUT_TMPL={shlex.quote(str(path('resume_out')))}")
print("typeset -A V")
print("V=(" + " ".join(f"{shlex.quote(k)} {shlex.quote(v)}" for k, v in c["resume_variants"].items()) + ")")
PY
)"
arg=${1:-default}
if [[ -n ${V[$arg]} ]]; then tex=${V[$arg]%%:*}; suf=${V[$arg]#*:}
else tex=${arg:t:r}; suf=${2:-${tex#*_}}; fi
[[ -n $2 ]] && suf=$2
cd $R
[[ -f $tex.tex ]] || { echo "no $R/$tex.tex"; exit 1; }
PDFLATEX=$(command -v pdflatex || echo /opt/homebrew/bin/pdflatex)
$PDFLATEX -interaction=nonstopmode -halt-on-error $tex.tex > /tmp/rb_$$.log 2>&1 || { echo "编译失败："; grep -m5 -A3 "^!" /tmp/rb_$$.log; exit 1; }
grep -q "Missing character" $tex.log && { echo "⚠️ 有字符没渲染（多半是中文）："; grep "Missing character" $tex.log | head -3; exit 1; }
pages=$(python3 -c "import fitz;print(fitz.open('$tex.pdf').page_count)" 2>/dev/null || /usr/bin/mdls -raw -name kMDItemNumberOfPages $tex.pdf)
out=${OUT_TMPL//\{suffix\}/${suf:+_$suf}}
cp $tex.pdf $out
echo "$tex.tex → $out  (${pages} 页)"
(( pages <= 2 )) || echo "⚠️ 超过 2 页"
