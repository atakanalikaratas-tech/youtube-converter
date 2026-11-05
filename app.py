import os
import re
import tempfile
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import yt_dlp

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

app = Flask(__name__)
CORS(app)

def clean_youtube_url(url):
    """Linkte &list= veya playlist parametreleri varsa temizler, sadece tek videoya odaklar."""
    match = re.search(r'(https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+)', url)
    if match:
        return match.group(1)
    match_short = re.search(r'(https?://youtu\.be/[\w-]+)', url)
    if match_short:
        return match_short.group(1)
    return url

COMMON_YTDL_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios', 'web']
        }
    }
}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/info', methods=['POST'])
def get_video_info():
    raw_url = request.json.get('url')
    if not raw_url:
        return jsonify({'error': 'Bağlantı adresi gerekli.'}), 400

    url = clean_youtube_url(raw_url)

    try:
        with yt_dlp.YoutubeDL(COMMON_YTDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = info.get('formats', [])
            resolutions = set()
            for f in formats:
                if f.get('vcodec') != 'none' and f.get('height'):
                    resolutions.add(f"{f['height']}p")
            
            sorted_res = sorted(list(resolutions), key=lambda x: int(x.replace('p', '')), reverse=True)

            return jsonify({
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration_string'),
                'resolutions': sorted_res,
                'clean_url': url
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['GET'])
def download_video():
    raw_url = request.args.get('url')
    format_type = request.args.get('format', 'mp4')
    quality = request.args.get('quality', '720p')

    if not raw_url:
        return "Bağlantı bulunamadı", 400

    url = clean_youtube_url(raw_url)
    temp_dir = tempfile.mkdtemp()
    output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')

    ydl_opts = dict(COMMON_YTDL_OPTS)
    ydl_opts['outtmpl'] = output_template

    if format_type == 'mp3':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        height = quality.replace('p', '')
        ydl_opts['format'] = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]/best'
        ydl_opts['merge_output_format'] = 'mp4'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if format_type == 'mp3':
                filename = os.path.splitext(filename)[0] + '.mp3'

        return send_file(filename, as_attachment=True)
    except Exception as e:
        return f"İndirme hatası: {str(e)}", 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
