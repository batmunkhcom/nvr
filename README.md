# NVR System

Олон төрлийн IP камеруудыг (ONVIF, RTSP, Hikvision, Dahua, Axis, Reolink зэрэг)
төвлөрсөн удирдлагаар хянах, бичлэг хийх, AI-аар объект таних, хөдөлгөөн илрүүлэх
Network Video Recorder систем.

## Быстрая старт

```bash
# Инфраструктур эхлүүлэх
make infra

# Тохиргоог анхлан ачаалах
make seed

# API сервер ажиллуулах
make dev
```

## Бүрэн баримт бичиг

[PLAN.md](docs/PLAN.md) — Архитектур төлөвлөгөө, API spec, DB schema

## Хөгжүүлэлт

[AGENTS.md](AGENTS.md) — AI хөгжүүлэлтийн чиглүүлэг
