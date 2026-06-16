"""
login_tracker.py — place in project root next to manage.py
Call record_login(request, user) right after auth_login() in login_view.
"""
import re, threading

def _parse_ua(ua):
    if not ua:
        return dict(browser='', browser_ver='', os_name='', os_ver='', device_type='Desktop', device_name='')
    browser, bver = '', ''
    for name, pat in [('Edge','Edg(?:e)?/([\\d.]+)'),('Chrome','Chrome/([\\d.]+)'),
                       ('Firefox','Firefox/([\\d.]+)'),('Safari','Version/([\\d.]+).*Safari'),
                       ('Opera','OPR/([\\d.]+)'),('MSIE','MSIE ([\\d.]+)')]:
        m = re.search(pat, ua, re.I)
        if m: browser, bver = name, m.group(1); break
    os_name, osver = '', ''
    for name, pat in [('Windows 11','Windows NT 10\\.0.*Win64'),('Windows 10','Windows NT 10\\.0'),
                       ('Windows 7','Windows NT 6\\.1'),('macOS','Mac OS X ([\\d_]+)'),
                       ('Android','Android ([\\d.]+)'),('iOS','iPhone OS ([\\d_]+)'),('Linux','Linux')]:
        m = re.search(pat, ua, re.I)
        if m: os_name = name; osver = m.group(1).replace('_','.') if m.lastindex else ''; break
    device = 'Tablet' if re.search(r'iPad|tablet', ua, re.I) else \
             'Mobile' if re.search(r'Mobi|Android|iPhone', ua, re.I) else 'Desktop'
    dname = ''
    m = re.search(r'\(([^)]+)\)', ua)
    if m: dname = m.group(1)[:200]
    return dict(browser=browser, browser_ver=bver, os_name=os_name, os_ver=osver,
                device_type=device, device_name=dname)

def _get_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')

def _geo(ip):
    try:
        if not ip or ip in ('127.0.0.1', '::1'):
            return dict(country='Local', region_geo='', city='Localhost', isp='')
        import requests as _r
        d = _r.get(f'http://ip-api.com/json/{ip}?fields=country,regionName,city,isp', timeout=4).json()
        return dict(country=d.get('country',''), region_geo=d.get('regionName',''),
                    city=d.get('city',''), isp=d.get('isp',''))
    except Exception:
        return dict(country='', region_geo='', city='', isp='')

def record_login(request, user):
    ip  = _get_ip(request)
    ua  = request.META.get('HTTP_USER_AGENT', '')
    sk  = request.session.session_key or ''
    ua_data = _parse_ua(ua)
    def _save():
        from marketing.models import UserLoginLog
        geo = _geo(ip)
        UserLoginLog.objects.create(user=user, ip_address=ip or None,
                                    user_agent=ua[:2000], session_key=sk,
                                    **ua_data, **geo)
    threading.Thread(target=_save, daemon=True).start()