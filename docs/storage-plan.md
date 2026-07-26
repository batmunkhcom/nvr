# Storage System — Бүрэн Төлөвлөгөө

Огноо: 2026-07-26

## Одоогийн Асуудлууд

| # | Асуудал | Тайлбар |
|---|---------|---------|
| 1 | Docker named volume | `recordings` volume → `/var/lib/docker/volumes/` дотор хадгалагдаж, хост `/data`-тай холбоогүй |
| 2 | Админ panel ↔ recording engine холбоогүй | Админаас тохируулсан `mount_point`-ийг recording engine огт уншдаггүй. Зөвхөн `STORAGE_LOCAL_PATH` env var ашигладаг |
| 3 | `recordings.storage_backend_id` | Үргэлж `NULL` — catalog бөглөдөггүй |
| 4 | NFS/SMB класс байхгүй | `storage.py`-д `LocalStorage`, `S3Storage` л бий. `NFSStorage`, `SMBStorage` байхгүй |
| 5 | NFS/SMB mount логик байхгүй | mount/unmount/health-check код огт байхгүй |
| 6 | S3 post-write upload байхгүй | Recording engine local-д бичээд S3 руу хуулах worker байхгүй |
| 7 | Storage tiers ашиглагдахгүй | `storage_tiers` хүснэгт бий, харин migration worker байхгүй |

---

## Phase 1: Foundation — Local Storage Админтай Холбогдох

**Зорилго:** Админ панел дээр тохируулсан `mount_point` бодит бичлэг хадгалах зам болох, Docker bind mount-р хост диск рүү шууд бичих.

### Өөрчлөгдөх файлууд

| # | Файл | Өөрчлөлт |
|---|------|----------|
| 1 | `docker-compose.yml` | `recordings:/data/recordings` → `${STORAGE_HOST_PATH:-/data}:/data/recordings` (nvr-api, nvr-recording-engine, nvr-ai-engine). `volumes:` секцнээс `recordings:` устгах |
| 2 | `docker-compose.prod.yml` | `nvr-recording-engine`, `nvr-ai-engine`-д `recordings` volume mount нэмэх (prod-д код volumes хасагдсан учраас `recordings` mount мөн хасагдсан) |
| 3 | `.env` | `STORAGE_HOST_PATH=/data` нэмэх |
| 4 | `.env.example` | `STORAGE_HOST_PATH=/data` нэмэх, тайлбартай |
| 5 | `services/recording-engine/app/config.py` | `resolve_storage_path(session)` нэмэх — DB-с идэвхтэй local backend-ийн `mount_point` унших, `STORAGE_LOCAL_PATH` env-д fallback |
| 6 | `services/recording-engine/app/main.py` | Startup дээр `resolve_storage_path()` дуудаж `config.STORAGE_LOCAL_PATH`-г дарна. Үлдсэн бүх код (recorder, catalog, retention, analytics, motion) өөрчлөгдөхгүй |
| 7 | `services/api/app/services/recording_service.py` | `get_storage_usage()` fallback: hardcoded `"/data/recordings"` → `STORAGE_LOCAL_PATH` env |
| 8 | `packages/common/nvr_common/storage.py` | `S3Storage`: multipart upload нэмэх, `total_bytes`/`available_bytes` бодит S3 API-с авах |

### Docker Mount Flow (Phase 1-ийн дараа)

```
Хост /data/  ──bind mount──▶  Контейнер /data/recordings/
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            recording-engine   nvr-api         nvr-ai-engine
            (бичлэг бичих)   (stream хийх)   (snapshot хадгалах)
                    │
                    ▼
      /data/recordings/{camera_id}/YYYY/MM/DD/*.mp4
```

### Админ панел тохиргоо

```
Storage → Backends → Create:
  name: "Local Storage"
  backend_type: local
  mount_point: /data/recordings
  priority: 1
```

### Шилжилтийн алхмууд

```bash
# 1. Зогсоох
docker compose down

# 2. Docker volume → хост диск
sudo cp -a /var/lib/docker/volumes/nvr_recordings/_data/* /data/

# 3. Файлуудыг засах (дээрх 8 файл)

# 4. Асаах
docker compose up -d

# 5. Админ panel → storage backend үүсгэх

# 6. Баталгаажуулах:
#    - recording-engine лог: "storage_path_resolved path=/data/recordings"
#    - Storage хуудасны disk usage зөв харуулж байгаа эсэх
```

---

## Phase 2: NFS / SMB Дэмжлэг

**Зорилго:** Хэрэглэгч NFS эсвэл SMB сервер рүү бичлэг хадгалах боломжтой болгох. Mount-ийг хост дээр хийж, Docker bind mount-р контейнерт оруулна.

**Архитектур:** NFS/SMB нь файлын системийн түвшинд `LocalStorage`-той адил ажиллана — зөвхөн stale mount илрүүлэх, эрүүл мэндийн шалгалт нэмэгдэнэ.

### Өөрчлөгдөх файлууд

| # | Файл | Өөрчлөлт |
|---|------|----------|
| 1 | `packages/common/nvr_common/storage.py` | `NFSStorage(LocalStorage)` класс — stale mount илрүүлэлт (`.nfs_health` файл бичиж/уншиж шалгах, timeout хамгаалалт) |
| 2 | `packages/common/nvr_common/storage.py` | `SMBStorage(LocalStorage)` класс — мөн адил |
| 3 | `services/api/app/services/recording_service.py` | `get_storage_usage()` — NFS/SMB-д `shutil.disk_usage` хийхээс өмнө stale mount шалгах, `health_status` шинэчлэх |
| 4 | `services/web/src/pages/Storage.tsx` | NFS/SMB backend үүсгэх dialog дээр mount заавар харуулах |

### NFS Backend Үүсгэх Заавар (Жишээ)

Админ panel дээр NFS backend үүсгэхэд дараах зааврыг харуулна:

```
# 1. Хост дээр mount цэг үүсгэх
sudo mkdir -p /mnt/nvr_nfs

# 2. NFS share mount хийх
sudo mount -t nfs -o nfsvers=4 192.168.1.100:/volume1/nvr /mnt/nvr_nfs

# 3. fstab-д бүртгэх (reboot-д автоматаар mount хийх)
echo "192.168.1.100:/volume1/nvr /mnt/nvr_nfs nfs nfsvers=4 0 0" | sudo tee -a /etc/fstab

# 4. docker-compose.override.yml үүсгэх:
services:
  nvr-recording-engine:
    volumes:
      - /mnt/nvr_nfs:/mnt/nvr_nfs
  nvr-api:
    volumes:
      - /mnt/nvr_nfs:/mnt/nvr_nfs
  nvr-ai-engine:
    volumes:
      - /mnt/nvr_nfs:/mnt/nvr_nfs

# 5. Асаах
docker compose up -d
```

### SMB Backend Үүсгэх Заавар (Жишээ)

```
# 1. CIFS хэрэгсэл суулгах
sudo apt install -y cifs-utils

# 2. Mount хийх
sudo mkdir -p /mnt/nvr_smb
sudo mount -t cifs -o username=user,password=pass //192.168.1.101/nvr /mnt/nvr_smb

# Үлдсэн алхмууд NFS-тэй адил
```

---

## Phase 3: S3 Post-Write Upload

**Зорилго:** Бичлэгүүдийг эхлээд local-д хурдан бичиж, хаагдсан сегментийг S3 (AWS S3 эсвэл өөр S3-compatible storage) руу асинхроноор upload хийх.

**Архитектур:** Recording engine local-д бичнэ → Catalog хаагдсан сегментийг DB-д бүртгэнэ → `S3SyncWorker` upload хийж `storage_backend_id` + `file_path` шинэчилнэ.

### Өөрчлөгдөх/Шинээр үүсэх файлууд

| # | Файл | Өөрчлөлт |
|---|------|----------|
| 1 | `services/recording-engine/app/s3_sync.py` | **Шинэ** — `S3SyncWorker`: 60 сек тутамд `storage_backend_id IS NULL` + S3 backend-тэй камерын recording-үүдийг шалгаж `copy_to()` хийх. Амжилттай бол `storage_backend_id`, `file_path` шинэчлэх |
| 2 | `services/recording-engine/app/catalog.py` | `_register()` — S3 backend-тэй камерын recording-д `storage_backend_id=NULL` үлдээх (s3_sync worker хариуцна) |
| 3 | `services/recording-engine/app/main.py` | `s3_sync_loop` нэмэх |

### S3 Upload Flow

```
1. Recorder:           local-д /data/recordings/{camera_id}/.../*.mp4 бичих
2. Catalog.scan():     segment DB-д бүртгэх
                         → storage_backend_id = NULL
                         → file_path = /data/recordings/{cid}/.../file.mp4 (local)
3. S3SyncWorker:
   a. camera.storage_backend_id → S3 backend-ийн тохиргоог авах
   b. StorageBackend.copy_to(local_path, s3_backend, s3_path)
   c. Амжилттай бол:
        UPDATE recordings SET storage_backend_id = <s3_id>,
          file_path = 's3://bucket/{cid}/.../file.mp4'
   d. Local file устгах (retention хэсэг хариуцна, эсвэл sync worker шууд устгах)
4. API stream:         file_path s3:// эсэхийг шалгаж S3-с stream хийх
```

---

## Phase 4: Storage Tiers & Migration

**Зорилго:** Бичлэгүүдийг насжилтаар нь өөр өөр backend руу зөөх (hot → warm → cold).

### Өөрчлөгдөх/Шинээр үүсэх файлууд

| # | Файл | Өөрчлөлт |
|---|------|----------|
| 1 | `services/api/app/api/v1/storage.py` | Storage tiers CRUD endpoint (одоо зөвхөн backends CRUD бий, tiers байхгүй) |
| 2 | `services/recording-engine/app/tier_migration.py` | **Шинэ** — `TierMigrationWorker`: tier тохиргоогоор recording-үүдийг зөөх |
| 3 | `services/recording-engine/app/main.py` | `tier_migration_loop` нэмэх |
| 4 | `services/web/src/pages/Storage.tsx` | Tiers удирдах tab |

### Tier Migration Flow

```
storage_tiers хүснэгт:
  hot  (priority=1, retention=7d)   → local SSD
  warm (priority=2, retention=30d)  → NFS HDD
  cold (priority=3, retention=365d) → S3 архив

TierMigrationWorker (цаг тутам):
  1. Tier бүрийн насжилт шалгах
  2. recording.start_time + tier.retention_days > now → дараагийн tier руу copy_to()
  3. storage_migrations хүснэгтэд бүртгэх
```

---

## S3 Backend vs Local Storage — Харьцуулалт

| | Local / NFS / SMB | S3 (AWS/MinIO) |
|---|---|---|
| Хурд | Маш хурдан (шууд диск) | Сүлжээний latency |
| Бичлэгийн үед | Шууд файлд бичих | Эхлээд local, дараа upload |
| Төвөгтэй байдал | Энгийн | Нарийн (multipart upload, retry, error handling) |
| Хэрэглээ | Дотоод NVR | Олон серверээс хандах, архивлах, CDN |
| Зардал | Дискний үнэ | S3 API зардал (AWS) эсвэл MinIO серверийн нөөц |

**Зөвлөмж:** Дан NVR суулгацад **Local storage хангалттай**. Хэрэв multi-node deployment эсвэл урт хугацааны архив шаардлагатай бол S3 нэмэх.

---

## Хэрэгжүүлэх Дараалал

```
Phase 1 (Foundation)    ◀── ЗААВАЛ хамгийн түрүүнд
   │
   ├── Phase 2 (NFS/SMB)    ◀── Хэрэгцээгээр
   │
   ├── Phase 3 (S3 upload)  ◀── Хэрэгцээгээр
   │
   └── Phase 4 (Tiers)      ◀── Phase 2,3-ийн дараа
```

---

## Статус

| Phase | Статус | Төлөвлөсөн хугацаа |
|-------|--------|-------------------|
| Phase 1 | Хийгдээгүй | ~30 мин |
| Phase 2 | Хийгдээгүй | ~1 цаг |
| Phase 3 | Хийгдээгүй | ~2 цаг |
| Phase 4 | Хийгдээгүй | ~2 цаг |
