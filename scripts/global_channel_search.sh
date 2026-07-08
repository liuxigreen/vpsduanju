#!/bin/bash
# 全球短剧频道批量搜索
# 用法: bash scripts/global_channel_search.sh

YTDLP="$HOME/.pyenv/shims/yt-dlp"
OUTDIR="$HOME/duanju/data/channel_search"
mkdir -p "$OUTDIR"

echo "=== 全球短剧频道搜索 ==="
echo "时间: $(date)"
echo ""

# 搜索函数
search_channels() {
    local region="$1"
    local query="$2"
    local count="${3:-5}"
    
    echo "--- [$region] $query ---"
    $YTDLP "ytsearch${count}:${query}" --flat-playlist \
        --print "%(channel)s|||%(channel_id)s|||%(title)s|||%(view_count)s" \
        2>/dev/null | while IFS='|||' read -r channel cid title views; do
        echo "  📺 $channel | $cid | $views views | ${title:0:60}"
    done
    echo ""
}

# ========== 中文市场 ==========
echo "====== 中文市场 ======"

# 女频
search_channels "女频_重生" "重生 短剧 全集" 8
search_channels "女频_总裁" "总裁 短剧 甜宠" 8
search_channels "女频_心声" "心声 短剧 全集" 8
search_channels "女频_赘婿" "赘婿 短剧 全集" 8
search_channels "女频_闪婚" "闪婚 短剧" 5
search_channels "女频_替嫁" "替嫁 短剧" 5

# 男频
search_channels "男频_战神" "战神 短剧 全集" 8
search_channels "男频_龙王" "龙王 短剧 全集" 8
search_channels "男频_神医" "神医 短剧 全集" 8
search_channels "男频_逆袭" "逆袭 短剧 逆袭" 5
search_channels "男频_至尊" "至尊 短剧" 5
search_channels "男频_归来" "归来 短剧" 5

# 粤语
search_channels "粤语_短剧" "粵語短劇" 8
search_channels "粤语_港剧" "港劇 短片" 5

# 台湾
search_channels "台湾_短剧" "台灣短劇" 8
search_channels "台湾_甜宠" "短劇 甜寵 台灣" 5

# ========== 东南亚 ==========
echo "====== 东南亚 ======"

search_channels "印尼_短剧" "drama pendek indonesia" 8
search_channels "印尼_CEO" "CEO drama indonesia" 5
search_channels "越南_短剧" "phim ngắn trung quốc" 8
search_channels "泰国_短剧" "ซีรี่ย์สั้น จีน" 8
search_channels "菲律宾_短剧" "filipino short drama" 5
search_channels "马来_短剧" "drama pendek melayu" 5

# ========== 南亚 ==========
echo "====== 南亚 ======"

search_channels "印度_短剧" "indian short drama" 8
search_channels "印度_hindi" "hindi short drama series" 8
search_channels "印度_tamil" "tamil short drama" 5
search_channels "印度_telugu" "telugu short drama" 5
search_channels "印度_竖屏" "indian vertical drama" 5

# ========== 东亚 ==========
echo "====== 东亚 ======"

search_channels "韩国_短剧" "한국 숏드라마" 8
search_channels "日本_短剧" "日本 ショートドラマ" 8

# ========== 英文市场 ==========
echo "====== 英文市场 ======"

search_channels "英文_CEO" "CEO short drama full" 8
search_channels "英文_Reborn" "reborn short drama full" 8
search_channels "英文_Revenge" "revenge short drama" 5
search_channels "英文_PoorGirl" "poor girl CEO drama" 5
search_channels "英文_Chinese" "chinese short drama english" 8

# ========== 拉美 ==========
echo "====== 拉美 ======"

search_channels "西语_短剧" "drama corto chino" 8
search_channels "葡语_短剧" "drama curto chinês" 8
search_channels "西语_CEO" "CEO drama español" 5

# ========== 中东北非 ==========
echo "====== 中东北非 ======"

search_channels "阿拉伯_短剧" "مسلسل قصير صيني" 5
search_channels "土耳其_短剧" "kısa dizi çin" 5

echo "=== 搜索完成 ==="
echo "数据保存在: $OUTDIR/"
