# parse_email.py
from flanker import mime
import base64

def parse_raw_email(raw):
    """
    raw: raw RFC822 message string
    returns: dict with subject, from, to, plain_text, html, attachments list
    """
    msg = mime.from_string(raw)
    out = {}
    out['subject'] = msg.subject if hasattr(msg, 'subject') else None
    out['from'] = str(msg.from_) if hasattr(msg, 'from_') else None
    out['to'] = [str(t) for t in msg.to] if hasattr(msg, 'to') and msg.to else []
    out['text'] = None
    out['html'] = None
    if msg.body:
        if hasattr(msg.body, 'text'):
            out['text'] = msg.body.text
        if hasattr(msg.body, 'html'):
            out['html'] = msg.body.html
    out['attachments'] = []
    if hasattr(msg, 'attachments') and msg.attachments:
        for a in msg.attachments:
            filename = a.filename or "attachment"
            data = a.payload
            try:
                b = data if isinstance(data, (bytes, bytearray)) else data.encode('utf-8', errors='ignore')
                b64 = base64.b64encode(b).decode('ascii')
            except Exception:
                b64 = None
            out['attachments'].append({'filename': filename, 'b64': b64, 'content_type': a.content_type})
    return out