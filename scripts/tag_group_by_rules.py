#!/usr/bin/env python3
"""
标签分组脚本 - 用Python规则替代MiMo API调用
输入：titles.json（标题+标签）
输出：tag_groups.json（按规则分组）
规则：题材词、情绪词、身份词、关系词、格式词、地区词、质量词、其他
"""

import json
import sys
from pathlib import Path
from collections import defaultdict, Counter

# 标签分组规则（基于印尼语和英语短剧标签）
TAG_RULES = {
    "genre": [
        # 题材词
        "drama", "romance", "action", "comedy", "thriller", "horror", "fantasy",
        "romantis", "aksi", "komedi", "seram", "fantasi", "drama", "romance",
        "cdrama", "kdrama", "jdrama", "tdrama", "thaidrama",
        "chinesedrama", "koreandrama", "japanesedrama", "thaidrama",
        "drama", "film", "movie", "series", "episode",
        "drama", "film", "serial", "sinetron", "ftv",
        "revenge", "reinkarnasi", "reborn", "time travel", "perjalananwaktu",
        "balasdendam", "balas dendam", "dendam",
        "romance", "cinta", "cintamanis", "romantis", "love",
        "action", "laga", "pertarungan", "fight",
        "mystery", "misterius", "misteri", "mystery",
        "supernatural", "gaib", "mistis", "magic",
        "historical", "sejarah", "kerajaan", "kingdom", "dynasty",
        "modern", "kontemporer", "masakini",
        "fantasy", "fantasi", "imajinasi",
        "comedy", "komedi", "lucu", "funny",
        "thriller", "suspense", "tension",
        "horror", "seram", "hantu", "ghost", "scary",
        "melodrama", "melodramatik",
        "slice of life", "kehidupan sehari-hari",
        "school", "sekolah", "kampus", "university",
        "office", "kantor", "workplace",
        "family", "keluarga", "family drama",
        "business", "bisnis", "perusahaan", "company",
        "medical", "dokter", "rumah sakit", "hospital",
        "military", "militer", "tentara", "soldier",
        "war", "perang", "peperangan",
        "police", "polisi", "detective", "detektif",
        "crime", "kriminal", "pencurian",
        "sports", "olahraga", "football", "soccer",
        "music", "musik", "singer", "penyanyi",
        "cooking", "masak", "chef", "restaurant",
        "fashion", "mode", "desainer", "designer",
        "travel", "perjalanan", "adventure", "petualangan",
        "sci-fi", "fiksi ilmiah", "robot", "AI",
        "animation", "anime", "kartun", "cartoon",
        "documentary", "dokumenter",
        "reality show", "reality", "kompetisi", "competition",
    ],
    "emotion": [
        # 情绪词
        "cinta", "love", "romance", "romantis", "sweet", "manis",
        "sedih", "sad", "tragic", "tragis", "heartbreak", "patah hati",
        "marah", "angry", "rage", "kemarahan",
        "takut", "scared", "afraid", "fear", "horror",
        "kaget", "shocked", "surprise", "kejutan",
        "bahagia", "happy", "joy", "suka cita",
        "benci", "hate", "hatred", "dendam",
        "cemburu", "jealous", "envy", "iri",
        "malu", "shame", "embarrassed", "malu",
        "bersalah", "guilty", "regret", "penyesalan",
        "harapan", "hope", "hopeful", "berharap",
        "putus asa", "desperate", "hopeless",
        "rindu", "miss", "longing", "kangen",
        "syukur", "grateful", "thankful",
        "irihati", "envy", "jealousy",
        "sakit", "pain", "hurt", "suffering", "penderitaan",
        "tears", "air mata", "cry", "menangis",
        "smile", "senyum", "tawa", "laugh",
        "anger", "kemarahan", "fury", "murka",
        "fear", "ketakutan", "terror", "teror",
        "surprise", "kejutan", "shock", "kejut",
        "disgust", "jijik", "muak", "nausea",
        "trust", "percaya", "faith", "iman",
        "anticipation", "antisipasi", "expectation",
    ],
    "identity": [
        # 身份词
        "ceo", "boss", "president", "direktur", "director",
        "billionaire", "miliarder", "jutawan", "millionaire",
        "prince", "putra", "princess", "putri", "raja", "king", "ratu", "queen",
        "emperor", "kaisar", "empress", "permaisuri",
        "warrior", "pejuang", "pahlawan", "hero",
        "soldier", "tentara", "prajurit", "military",
        "doctor", "dokter", "paramedis", "paramedic",
        "lawyer", "pengacara", "advokat", "attorney",
        "teacher", "guru", "dosen", "professor",
        "student", "siswa", "mahasiswa", "pelajar",
        "nurse", "perawat", "suster",
        "driver", "supir", "sopir", "chauffeur",
        "maid", "pembantu", "ART", "housekeeper",
        "secretary", "sekretaris", "asisten", "assistant",
        "bodyguard", "pengawal", "security",
        "assassin", "pembunuh", "killer",
        "thief", "pencuri", "maling", "criminal",
        "beggar", "pengemis", "gelandangan", "homeless",
        "orphan", "yatim piatu", "anak terlantang",
        "widow", "janda", "duda", "widower",
        "divorcee", "cerai", "divorced",
        "single", "lajang", "single parent",
        "married", "menikah", "suami", "husband", "istri", "wife",
        "parent", "orang tua", "ayah", "father", "ibu", "mother",
        "child", "anak", "putra", "son", "putri", "daughter",
        "sibling", "saudara", "kakak", "adik",
        "friend", "teman", "sahabat", "bestfriend",
        "enemy", "musuh", "rival", "pesaing",
        "lover", "kekasih", "pacar", "boyfriend", "girlfriend",
        "ex", "mantan", "former",
        "twin", "kembar", "identical",
        "cousin", "sepupu",
        "aunt", "bibi", "uncle", "paman",
        "grandparent", "kakek", "nenek", "grandfather", "grandmother",
        "in-law", "mertua", "besan",
        "step", "tiri", "stepchild", "stepmother", "stepfather",
        "adopted", "adopsi", "foster",
        "disabled", "cacat", "lumpuh", "paralyzed",
        "amnesia", "lupa ingatan", "memory loss",
        "terminal", "sakit keras", "dying",
        "pregnant", "hamil", "mengandung",
        "baby", "bayi", "newborn",
        "teenager", "remaja", "ABG",
        "adult", "dewasa", "mature",
        "elderly", "lansia", "tua",
        "young", "muda", "youth",
        "rich", "kaya", "wealthy", "miskin", "poor",
        "powerful", "berkuasa", "influential",
        "famous", "terkenal", "celebrity", "artis",
        "unknown", "tidak dikenal", "anonymous",
        "commoner", "rakyat jelata", "ordinary",
        "noble", "bangsawan", "aristocrat",
        "commoner", "rakyat biasa", "平民",
        "commoner", "rakyat biasa", "平民",
    ],
    "relationship": [
        # 关系词
        "marriage", "pernikahan", "nikah", "wedding",
        "divorce", "cerai", "perpisahan",
        "affair", "perselingkuhan", "cheating",
        "betrayal", "pengkhianatan", "backstab",
        "reunion", "reuni", "bersatu kembali",
        "separation", "perpisahan", "berpisah",
        "conflict", "konflik", "pertentangan",
        "rivalry", "persaingan", "kompetisi",
        "friendship", "persahabatan", "sahabat",
        "family", "keluarga", "famili",
        "parent-child", "orang tua-anak",
        "sibling", "saudara",
        "romantic", "romantis", "cinta",
        "love triangle", "cinta segitiga",
        "enemies to lovers", "musuh jadi kekasih",
        "friends to lovers", "teman jadi kekasih",
        "fake relationship", "hubungan palsu",
        "contract marriage", "nikah kontrak",
        "arranged marriage", "perjodohan",
        "forced marriage", "nikah paksa",
        "secret relationship", "hubungan rahasia",
        "forbidden love", "cinta terlarang",
        "unrequited love", "cinta bertepuk sebelah tangan",
        "second chance", "kesempatan kedua",
        "reconciliation", "rekonsiliasi",
        "forgiveness", "pengampunan",
        "revenge", "balas dendam",
        "justice", "keadilan",
        "redemption", "penebusan",
        "sacrifice", "pengorbanan",
        "protection", "perlindungan",
        "mentorship", "bimbingan",
        "rivalry", "persaingan",
        "alliance", "aliansi",
        "partnership", "kemitraan",
        "trust", "kepercayaan",
        "betrayal", "pengkhianatan",
        "deception", "penipuan",
        "manipulation", "manipulasi",
        "conspiracy", "konspirasi",
        "intrigue", "intrik",
        "power struggle", "perebutan kekuasaan",
        "inheritance", "warisan",
        "legacy", "wasiat",
        "succession", "pewaris",
        "dynasty", "dinasti",
        "empire", "kekaisaran",
        "kingdom", "kerajaan",
        "throne", "takhta",
        "crown", "mahkota",
        "nobility", "k bangsawan",
        "aristocracy", "aristokrasi",
        "commoner", "rakyat jelata",
        "commoner", "rakyat biasa",
    ],
    "format": [
        # 格式词
        "full episode", "episode lengkap", "full series",
        "part", "bagian", "episode",
        "series", "serial", "seri",
        "movie", "film", "layar lebar",
        "short film", "film pendek",
        "drama", "sinetron", "ftv",
        "web series", "serial web",
        "mini series", "serial mini",
        "drama series", "serial drama",
        "film drama", "drama film",
        "episode 1", "episode 2", "episode 3",
        "ep 1", "ep 2", "ep 3",
        "part 1", "part 2", "part 3",
        "bagian 1", "bagian 2", "bagian 3",
        "chapter 1", "chapter 2", "chapter 3",
        "bab 1", "bab 2", "bab 3",
        "volume 1", "volume 2", "volume 3",
        "season 1", "season 2", "season 3",
        "musim 1", "musim 2", "musim 3",
        "full movie", "film lengkap",
        "full series", "serial lengkap",
        "complete", "lengkap", "komplit",
        "subtitle", "sub", "subtitle indonesia",
        "subtitle english", "subtitle chinese",
        "dubbing", "dub", "dubbing indonesia",
        "dubbing english", "dubbing chinese",
        "multi subtitle", "multi sub", "multisub",
        "hardsub", "softsub",
        "HD", "high definition", "4K", "UHD",
        "SD", "standard definition",
        "720p", "1080p", "480p",
        "bluray", "web-dl", "webrip",
        "cam", "ts", "tc",
        "official", "resmi", "legal",
        "unofficial", "tidak resmi", "illegal",
        "fanmade", "buatan penggemar",
        "original", "orisinal", "asli",
        "remake", "versi baru",
        "sequel", "sekuel", "lanjutan",
        "prequel", "prekuel", "awal",
        "spin-off", "spinoff",
        "adaptasi", "adaptation",
        "live action", "live-action",
        "animated", "animasi",
        "animated series", "serial animasi",
        "anime", "manga",
        "webtoon", "webnovel",
        "light novel", "novel ringan",
        "audiobook", "buku audio",
        "podcast", "podcast",
        "behind the scenes", "di balik layar",
        "bloopers", "kesalahan",
        "interview", "wawancara",
        "review", "ulasan",
        "reaction", "reaksi",
        "compilation", "kompilasi",
        "best of", "terbaik",
        "top 10", "top 5", "top 20",
        "highlight", "sorotan",
        "trailer", "teaser",
        "preview", "cuplikan",
        "sneak peek", "bocoran",
        "exclusive", "eksklusif",
        "bonus", "bonus",
        "special", "spesial",
        "final", "akhir",
        "ending", "akhir",
        "conclusion", "kesimpulan",
        "finale", "final",
        "premiere", "perdana",
        "debut", "debut",
        "launch", "peluncuran",
        "release", "rilis",
        "coming soon", "segera hadir",
        "new", "baru",
        "latest", "terbaru",
        "trending", "tren",
        "viral", "viral",
        "popular", "populer",
        "hot", "panas",
        "best", "terbaik",
        "top", "teratas",
        "must watch", "wajib tonton",
        "recommended", "rekomendasi",
        "wajib", "must",
        "harus", "should",
        "jangan lupa", "don't forget",
        "subscribe", "berlangganan",
        "like", "suka",
        "share", "bagikan",
        "comment", "komentar",
        "follow", "ikuti",
        "notification", "notifikasi",
        "bell", "lonceng",
        "turn on notifications", "aktifkan notifikasi",
    ],
    "region": [
        # 地区词
        "indonesia", "indonesian", "indo",
        "china", "chinese", "cina", "tiongkok",
        "korea", "korean", "korea",
        "japan", "japanese", "jepang",
        "thailand", "thai", "thailand",
        "vietnam", "vietnamese", "vietnam",
        "philippines", "filipino", "filipina",
        "malaysia", "malay", "malaysia",
        "singapore", "singaporean", "singapura",
        "brunei", "bruneian", "brunei",
        "myanmar", "burmese", "myanmar",
        "cambodia", "khmer", "kamboja",
        "laos", "lao", "laos",
        "taiwan", "taiwanese", "taiwan",
        "hong kong", "hongkong", "hong kong",
        "macau", "macanese", "macau",
        "india", "indian", "india",
        "pakistan", "pakistani", "pakistan",
        "bangladesh", "bangladeshi", "bangladesh",
        "sri lanka", "sri lankan", "sri lanka",
        "nepal", "nepali", "nepal",
        "bhutan", "bhutanese", "bhutan",
        "maldives", "maldivian", "maladewa",
        "middle east", "timur tengah",
        "arab", "arabic", "arab",
        "turkey", "turkish", "turki",
        "iran", "persian", "iran",
        "israel", "israeli", "israel",
        "jordan", "jordanian", "yordania",
        "lebanon", "lebanese", "lebanon",
        "syria", "syrian", "suriah",
        "iraq", "iraqi", "irak",
        "egypt", "egyptian", "mesir",
        "morocco", "moroccan", "maroko",
        "algeria", "algerian", "aljazair",
        "tunisia", "tunisian", "tunisia",
        "libya", "libyan", "libya",
        "sudan", "sudanese", "sudan",
        "ethiopia", "ethiopian", "ethiopia",
        "kenya", "kenyan", "kenya",
        "nigeria", "nigerian", "nigeria",
        "south africa", "south african", "afrika selatan",
        "europe", "eropa",
        "america", "amerika", "usa", "us",
        "united states", "amerika serikat",
        "canada", "canadian", "kanada",
        "united kingdom", "inggris", "uk",
        "germany", "german", "jerman",
        "france", "french", "prancis",
        "italy", "italian", "italia",
        "spain", "spanish", "spanyol",
        "portugal", "portuguese", "portugis",
        "russia", "russian", "rusia",
        "australia", "australian", "australia",
        "new zealand", "new zealand", "selandia baru",
        "brazil", "brazilian", "brasil",
        "mexico", "mexican", "meksiko",
        "argentina", "argentine", "argentina",
        "colombia", "colombian", "kolombia",
        "peru", "peruvian", "peru",
        "chile", "chilean", "chili",
        "venezuela", "venezuelan", "venezuela",
        "ecuador", "ecuadorian", "ekuador",
        "bolivia", "bolivian", "bolivia",
        "paraguay", "paraguayan", "paraguay",
        "uruguay", "uruguayan", "uruguay",
        "guyana", "guyanese", "guyana",
        "suriname", "surinamese", "suriname",
        "french guiana", "guyana perancis",
        "central america", "amerika tengah",
        "caribbean", "karibia",
        "asia", "asia",
        "africa", "afrika",
        "europe", "eropa",
        "north america", "amerika utara",
        "south america", "amerika selatan",
        "oceania", "oseania",
        "global", "global", "dunia", "world",
        "international", "internasional",
        "local", "lokal", "domestic", "domestik",
        "regional", "regional",
        "worldwide", "seluruh dunia",
    ],
    "quality": [
        # 质量词
        "full", "lengkap", "complete", "komplit",
        "hd", "high definition", "4k", "uhd",
        "sd", "standard definition",
        "720p", "1080p", "480p",
        "bluray", "web-dl", "webrip",
        "cam", "ts", "tc",
        "official", "resmi", "legal",
        "unofficial", "tidak resmi",
        "original", "orisinal", "asli",
        "exclusive", "eksklusif",
        "premium", "premium",
        "best", "terbaik", "top",
        "high quality", "kualitas tinggi",
        "low quality", "kualitas rendah",
        "clear", "jernih", "sharp", "tajam",
        "blurry", "kabur", "pixelated",
        "good", "bagus", "great", "hebat",
        "bad", "buruk", "terrible", "mengerikan",
        "excellent", "sangat bagus", "outstanding", "luar biasa",
        "perfect", "sempurna",
        "awesome", "menakjubkan", "amazing", "luar biasa",
        "wonderful", "indah", "beautiful", "cantik",
        "ugly", "jelek", "horrible", "mengerikan",
        "nice", "bagus", "fine", "baik",
        "cool", "keren", "awesome", "menakjubkan",
        "hot", "panas", "sexy", "seksi",
        "cute", "imut", "adorable", "menggemaskan",
        "handsome", "tampan", "good looking",
        "pretty", "cantik", "beautiful", "indah",
        "attractive", "menarik", "appealing",
        "boring", "membosankan", "dull", "membosankan",
        "interesting", "menarik", "fascinating", "memukau",
        "exciting", "mendebarkan", "thrilling", "mendebarkan",
        "emotional", "emosional", "touching", "mengharukan",
        "sad", "sedih", "tragic", "tragis",
        "happy", "bahagia", "joyful", "gembira",
        "funny", "lucu", "hilarious", "kocak",
        "scary", "menakutkan", "terrifying", "mengerikan",
        "romantic", "romantis", "sweet", "manis",
        "action-packed", "penuh aksi",
        "dramatic", "dramatis",
        "suspenseful", "penuh ketegangan",
        "mysterious", "misterius",
        "informative", "informatif",
        "educational", "edukatif",
        "entertaining", "menghibur",
        "addictive", "adiktif", "ketagihan",
        "binge-worthy", "layak ditonton terus",
        "must-watch", "wajib tonton",
        "recommended", "rekomendasi",
        "trending", "tren",
        "viral", "viral",
        "popular", "populer",
        "famous", "terkenal",
        "hit", "hit",
        "blockbuster", "blockbuster",
        "masterpiece", "karya agung",
        "classic", "klasik",
        "modern", "modern",
        "contemporary", "kontemporer",
        "traditional", "tradisional",
        "cultural", "budaya",
        "historical", "historis",
        "fictional", "fiksi",
        "realistic", "realistis",
        "fantasy", "fantasi",
        "sci-fi", "fiksi ilmiah",
        "animated", "animasi",
        "live-action", "live-action",
        "black and white", "hitam putih",
        "color", "berwarna",
        "silent", "bisu",
        "talkie", "bersuara",
        "subtitled", "bersubtitle",
        "dubbed", "dubbing",
        "multi-language", "multi bahasa",
        "bilingual", "dwibahasa",
        "trilingual", "trilingual",
        "multilingual", "multilingual",
    ],
    "other": []  # 默认组，不匹配其他规则的标签
}

def classify_tag(tag: str) -> str:
    """根据规则分类单个标签"""
    tag_lower = tag.lower().strip()
    
    # 检查每个规则组
    for group_name, keywords in TAG_RULES.items():
        if group_name == "other":
            continue
        for keyword in keywords:
            if keyword.lower() in tag_lower or tag_lower in keyword.lower():
                return group_name
    
    # 如果不匹配任何规则，返回"other"
    return "other"

def group_tags(titles_data: list) -> dict:
    """将所有标签按规则分组"""
    # 统计每个标签的出现次数和播放量
    tag_stats = defaultdict(lambda: {"count": 0, "total_views": 0, "group": "other"})
    
    for item in titles_data:
        views = item.get("views", 0)
        tags = item.get("description_tags", [])
        
        for tag in tags:
            if not tag or not tag.strip():
                continue
            
            tag_lower = tag.lower().strip()
            tag_stats[tag_lower]["count"] += 1
            tag_stats[tag_lower]["total_views"] += views
            
            # 分类（只在第一次遇到时分类）
            if tag_stats[tag_lower]["group"] == "other":
                tag_stats[tag_lower]["group"] = classify_tag(tag)
    
    # 按组整理
    groups = defaultdict(list)
    for tag, stats in tag_stats.items():
        group_name = stats["group"]
        groups[group_name].append({
            "tag": tag,
            "count": stats["count"],
            "total_views": stats["total_views"],
            "avg_views": stats["total_views"] // stats["count"] if stats["count"] > 0 else 0
        })
    
    # 每组内按播放量排序
    for group_name in groups:
        groups[group_name].sort(key=lambda x: x["avg_views"], reverse=True)
    
    return dict(groups)

def main():
    if len(sys.argv) < 2:
        print("用法: python3 tag_group_by_rules.py <titles.json> [output.json]")
        print("示例: python3 tag_group_by_rules.py distill/evidence/印尼/titles.json distill/evidence/印尼/tag_groups.json")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2]) if len(sys.argv) > 2 else input_file.parent / "tag_groups.json"
    
    if not input_file.exists():
        print(f"❌ 输入文件不存在: {input_file}")
        sys.exit(1)
    
    print(f"📖 读取: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        titles_data = json.load(f)
    
    print(f"📊 视频数: {len(titles_data)}")
    
    # 统计所有标签
    all_tags = []
    for item in titles_data:
        all_tags.extend(item.get("description_tags", []))
    print(f"🏷️  标签总数: {len(all_tags)}")
    
    # 分组
    print("🔄 按规则分组...")
    tag_groups = group_tags(titles_data)
    
    # 统计
    print("\n📈 分组统计:")
    total_tags = 0
    for group_name, tags in sorted(tag_groups.items()):
        print(f"  {group_name}: {len(tags)}个标签")
        total_tags += len(tags)
    print(f"  总计: {total_tags}个标签")
    
    # 保存
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(tag_groups, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 保存: {output_file}")
    print(f"📊 文件大小: {output_file.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    main()
