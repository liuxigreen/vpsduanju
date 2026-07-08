#!/usr/bin/env python3
"""清理非短剧大频道"""
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT / "data" / "competitor_data" / "latest.json"

# 明确的非短剧频道
REMOVE = {
    # 印度电影
    'Eros Universe',
    # 墨西哥/拉美电视台
    'Tlnovelas', 'Telemundo Series', 'Canal RCN', 'TV Azteca Novelas y Series',
    'Univision', 'Latina Televisión', 'Tele N', 'Tv Azteca Internacional',
    # 印尼电视台
    'Surya Citra Televisi (SCTV)', 'MDTV OFFICIAL', 'ANTV',
    # 土耳其电视台/剧评/电视剧
    'KanalD', 'Dizzy Dizi', 'Movies For Series', 'Celal Sevim', 'Turkish Showbiz',
    "Kaan'ın Tavsiyesi", 'melikşah altuntaş', 'Artistik Yapim',
    'Güller ve Günahlar', 'Çilek Kokusu', 'Sevdiğim Sensin', 'Senden Daha Güzel',
    'Daha 17', 'İlişki Durumu Karışık', 'Ruhun Duymaz', 'Gecenin Kraliçesi',
    'Aile Dizisi', 'Darmaduman', 'Bir Aşk Hikayesi', 'Ömer Dizisi', 'Seni Çok Bekledim',
    'Sahtekarlar', 'Kader Bağları', 'Yeraltı', 'Rüya', 'Doğanın Kanunu',
    "Halef: Köklerin Çağrısı", 'Patlamış Mısır',
    # 巴基斯坦/美国
    'Urdu 1 Official', 'Brat TV',
    # 音乐
    'UNIVERSAL MUSIC JAPAN', 'jamma desi', 'Dance Music MV', 'Sweet Love Melody',
    # 新闻/学习
    'NewsPicks /ニューズピックス', 'Deutsch lernen mit der DW', 'FluentU German',
    # 日本流媒体/综艺
    'Netflix Japan', 'Hulu Japan公式', 'DMM TV ドラマ【公式】', 'ABEMA ドラマ【公式】',
    'MBS（毎日放送）', 'しゅくろーから夜ふかし【しゅくかし】',
    # 电影频道
    'Moxi Movie Channel Spanish', 'SEU FILMES', 'Grandes Misterios',
    'Pelixo', 'Alas de Cine', 'Ultra Mex', 'FILME AMOR',
    'CiNENET Deutschland', 'SparkTV', 'Limon Tv',
    # 短片/非短剧
    'KIS KIS - keep it short', 'Carrot Productions', 'Period Drama',
    'Tracy Kleeman', 'Blake Ridder', 'D4Darious', 'Dark Horse Pictures',
    # 综艺/生活
    'Rohis TV', 'Lova Channel', 'ZakCINEMA',
    'Metro Matriculation Higher Secondary Sch', 'Grind Arts Company',
    # 其他
    'NicelyTV', 'Lifted - Stories That Inspire', 'Femme Fatales',
    'Top Cine & Tv', 'Don Filósofo', 'Ana Laura',
    '韓流エンタメ情報局', '9MI Shorts',
    'ZE_LFY', 'シコい社長', 'Me xừ Đức',
    'ABSURD Production', 'RAFF PICTURES & ENTERTAINMENT',
    'Nonton Asyik', 'Sinemaku21', 'Dellaroz', 'Tiro Timur', 'LIVE DRAW TOTO MACAU',
    'みかみ【東大退学させられた男】', '動画編集で人生を切り拓く-やまと',
    'きよあき@YouTubeショート攻略ch', '日本こそ至高なれ',
    'はるな*無職アラサーママの在宅ワーク生活', '爆笑ネッコ100連発!!',
    'Canvaデザイナー Sayaka', 'なむ', '智恵の実',
    'Méndez Visión', 'Alejandro Mandujano Lopez',
    'Elias Da Silva', 'DM Sandoval', 'Dora Santos', 'Jack Gireli',
    'Gabriela', 'RCN Novelas', 'Canal Novelas - Novelas Completas Español',
    'Mujer', 'Serie matutina', 'Series en Español. Completas',
    'Amor e Honra - Leke', 'Novelas da vida real',
    'Romance  Channel', 'CanelaTV',
    'Teatro de Dramas Curtos', 'CurtasDramáticos',
    'CONDIMENTOS PARA EL ALMA', 'MILLION DOLLAR CINEMA STUDIO',
    'strange love', 'ポテトピクチャーズ',
    'WeTV Indonesia - Get the WeTV APP', 'WeTV Spanish - Get the WeTV APP',
    'Películas Románticas', 'Teatro Maravilhoso', 'Ráfagas Dramáticas',
    'Latido Dorama',
    # vlog
    'ぜるふぃー / ZELLFY',
    # 非短剧
    'Chill Cream Cinema', 'Core Drama', 'DRM DRAMA Deutsch',
    'Epic Short Drama', 'DramaBox - Kurzdramen Streaming', 'Relate Drama',
    'SWIPEDRAMA', 'Drama Corto Plus',
}

data = json.loads(LATEST.read_text())
before = len(data)
data = [ch for ch in data if ch['name'] not in REMOVE]
after = len(data)

LATEST.write_text(json.dumps(data, ensure_ascii=False, indent=2))

print(f'清理: {before} → {after} (删除{before - after}个非短剧频道)')

print('\n语言分布:')
for lang, c in Counter(ch['language'] for ch in data).most_common():
    print(f'  {lang}: {c}')

print('\n剩余>100万订阅:')
for ch in sorted(data, key=lambda x: -x.get('subscribers',0))[:15]:
    name = ch.get('name','')[:30]
    subs = ch.get('subscribers',0)
    lang = ch.get('language','')
    print(f'  {subs:>12,}  {name:<32} {lang}')
