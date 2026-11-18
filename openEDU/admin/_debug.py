import requests

API_FLAT = "https://data.jsdelivr.com/v1/package/gh/HKBrianNg/img-library@main/flat"

print("请求地址:", API_FLAT)
r = requests.get(API_FLAT, timeout=30)
print("HTTP", r.status_code)

if r.status_code == 200:
    data = r.json()
    files = data.get("files", [])
    print("总文件数:", len(files))
    print("前 8 条:")
    for f in files[:8]:
        print(" ", repr(f))
else:
    print("响应内容:", r.text[:500])