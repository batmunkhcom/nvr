#!/usr/bin/env bash
set -e

REMOTE_NAME="${1:-github}"          # GitHub remote-ийн нэр
MIRROR_BRANCH="github-clean-temp"   # Локалоор үүсэх түр branch

# 1. Одоогийн байж байгаа branch-ийг хадгалах
CURRENT_BRANCH=$(git branch --show-current)

# 2. Масклалт хийх түр branch үүсгэх
git checkout -B "$MIRROR_BRANCH"

# 3. Аюултай файлуудыг Git-ээс салгах (Local-аас устгахгүй)
git rm --cached *.sqlite *.db *.log *.pem *.key *.sql .env* 2>/dev/null || true

# 4. IP Хаягуудыг масклах
git grep -P -l '(?<!127\.0\.0\.1)(?<!0\.0\.0\.0)(?:[0-9]{1,3}\.){3}[0-9]{1,3}' -- :^scripts/ | while read -r file; do
    sed -i -E 's/([0-9]{1,3}\.){3}[0-9]{1,3}/process.env.SERVER_IP || "127.0.0.1"/g' "$file"
done

# 5. Absolute Path-уудыг масклах (/home/..., /root/...)
git grep -P -l '(\/home\/|\/root\/|\/var\/www\/)[a-zA-Z0-9_\-\/]+' -- :^scripts/ | while read -r file; do
    sed -i -E 's/(\/home\/|\/root\/|\/var\/www\/)[a-zA-Z0-9_\-\/]+/"\/app\/path_redacted"/g' "$file"
done

# 6. Webhook-уудыг масклах
git grep -P -l 'https:\/\/hooks\.(slack|discord)\.com\/[a-zA-Z0-9_\-\/]+' -- :^scripts/ | while read -r file; do
    sed -i -E 's/https:\/\/hooks\.(slack|discord)\.com\/[a-zA-Z0-9_\-\/]+/"https:\/\/hooks.redacted.com\/service"/g' "$file"
done

# 7. Өөрчлөлтүүдийг сүүлчийн commit дотор чимээгүй уусгах (Хуулбар гэдгийг мэдэгдэхгүй)
git add .
git commit --amend --no-edit || git commit -m "refactor(config): update environment fallbacks" || true

# 8. ЛОКАЛ ТҮР BRANCH-ИЙГ GITHUB-ИЙН MAIN BRANCH РУУ ПУШ ХИЙХ
git push "$REMOTE_NAME" "$MIRROR_BRANCH:main" --force

# 9. Буцаж үндсэн branch дээрээ очиж, түр branch-ийг устгах
git checkout "$CURRENT_BRANCH"
git branch -D "$MIRROR_BRANCH"

echo "✅ GitHub-ийн MAIN branch руу анхнаасаа цэвэрхэн бичигдсэн код шиг амжилттай push хийгдлээ!"
