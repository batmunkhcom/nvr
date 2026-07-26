# Cross-Camera Object Tracking & 3D Reconstruction

> Судалгааны баримт бичиг — хэрэгжүүлэх төлөвлөгөө хараахан батлагдаагүй.

## Single-Camera IoU Tracking (Үе 1) — Хэрэгжиж байгаа

Одоогийн per-class dedup-г IoU-based multi-object tracklet tracking-ээр сольсон. Нэг камер доторх объект бүр тусдаа ID-тай, хөдөлгөөн тус бүрт cooldown тохируулсан.

---

## Cross-Camera Re-ID Engine (Үе 2) — Төлөвлөгөө

### Зорилго
Нэг машин/хүн А камераас гарч Б камерт орсон ч ижил ID-тай хянагдах.

### Архитектур

```
┌─────────────────────────────────────────────────┐
│                  AI Engine                        │
│                                                   │
│  FrameSampler (камер бүрт)                        │
│    ↓                                              │
│  IoU Tracking → Tracklet{id, bbox, cls}           │
│    ↓                                              │
│  Crop Extractor → 128x256 crop (np array)         │
│    ↓  (2 тусдаа зам: CPU-д хадгалах / GPU руу илгээх)
│    │                                              │
│    ├─ CPU зам: crop-уудыг дискэнд data хэлбэрээр хадгалах
│    │           (batch export → GPU серверт зөөх)
│    │
│    └─ GPU зам: ReID ONNX → 512-dim embedding
│         ↓                                         │
│    Redis Vector Store                              │
│    HSET reid:{cls} {track_id} → embedding (bytes)  │
│         ↓                                         │
│    Cross-Camera Matcher                            │
│    • Хөрш камеруудын embedding-үүдийг харьцуулна   │
│    • 3 секундын цонхоор хайна                      │
│    • Cosine similarity > 0.75 → global_track_id    │
└─────────────────────────────────────────────────┘
```

### Vision Re-ID загварын сонголтууд

| Загвар | ONNX хэмжээ | Embedding | CPU (per crop) | GPU T4 | Давуу тал |
|--------|------------|-----------|-----------------|--------|-----------|
| **OSNet x1.0** | ~8MB | 512-dim | ~5ms | ~1ms | Хүн/машин Re-ID-д зориулсан |
| **CLIP ViT-B/32** | ~600MB | 512-dim | ~15ms | ~3ms | Open-set, текст+зураг multimodal |
| **DINOv2 ViT-S** | ~88MB | 384-dim | ~10ms | ~2ms | General visual features |
| **FastReID** | ~20MB | 256-dim | ~3ms | ~1ms | Torchreid compatible |

**Зөвлөмж:** OSNet x1.0 — хамгийн хөнгөн, surveillance-д тусгайлан бүтээгдсэн, ONNX export хялбар.

### GPU серверт зориулсан data export

```python
# CPU дээр (одоогийн NVR):
# Object crop бүрийг дискэнд хадгалах
for tracklet in active_tracklets:
    crop = frame[y1:y2, x1:x2]
    crop_resized = cv2.resize(crop, (128, 256))
    path = f"/data/reid_exports/{camera_id}/{tracklet.id}_{timestamp}.jpg"
    cv2.imwrite(path, crop_resized, [cv2.IMWRITE_JPEG_QUALITY, 90])

# GPU серверт:
# ONNX модель ачаалж, batch-аар embedding гаргах
session = ort.InferenceSession("osnet_x1_0.onnx", providers=["CUDAExecutionProvider"])
embeddings = session.run(None, {"input": batch_crops})[0]
# → np.array shape: (N, 512)
```

### GPU тохиргоо (хэрэв GPU шууд ашиглах бол)

```yaml
# .env эсвэл system_config
AI_DEVICE=cpu              # cpu | cuda
AI_REID_ENABLED=false      # true | false
AI_REID_MODEL=osnet        # osnet | clip | dinov2
AI_REID_GPU_ID=0           # аль GPU индекс ашиглах
AI_REID_EXPORT=true        # CPU дээр crop-уудыг хадгалах
AI_REID_EXPORT_PATH=/data/reid_exports
```

### Гүйцэтгэлийн үнэлгээ

| Хэмжигдэхүүн | CPU (Re-ID-гүй) | GPU T4 (YOLO + Re-ID) |
|-------------|-----------------|----------------------|
| YOLOv8n detection | CPU 74% | GPU ~15% (CUDA) |
| Re-ID embedding | (байхгүй) | ~2% GPU |
| Нийт CPU | ~74% | ~30% |
| GPU (T4) | 0% | ~25% |
| RAM | ~565MB | ~800MB (+embedding cache) |

---

## 3D Орчны Зураглал (Үе 5) — Алсын төлөвлөгөө

### Боломжит аргууд

| Арга | Тайлбар | GPU | Боловсруулах хугацаа |
|------|---------|-----|---------------------|
| **SfM (COLMAP)** | Multi-view stereo → 3D point cloud | GPU шаардлагатай | Хэдэн цаг |
| **3D Gaussian Splatting** | NeRF variant, real-time rendering | GPU заавал | Хэдэн цаг |
| **Depth Anything V2** | Monocular depth estimation | GPU faster | Минут |
| **2D Overhead Map** | Practical: камерын FOV-г 2D plan дээр төсөөлөх | Хэрэггүй | Realtime |

### Дүгнэлт

3D reconstruction нь одоогийн системийн хүрээнд хэрэгжих боломжгүй:
- 4 CPU, 8GB RAM (GPU-гүй)
- Realtime processing шаардлагатай (3D нь offline)
- 100+ цаг CPU процесс эсвэл GPU сервер шаардлагатай

**Практик сонголт:** 2D overhead map + камерын FOV overlay (realtime, хөнгөн).

### 2D Overhead Map Viewer (Үе 4 — төлөвлөгөө)

```
        ┌──────────────────────────┐
        │    2D Floor Plan          │
        │                           │
        │   📷cam1 (NE, FOV 90°)    │
        │    ╲     ┌───┐            │
        │     ╲    │car│  ╱         │
        │      ╲   └───┘ ╱          │
        │       ╲   📷cam2 ╱        │
        │        ╲   ╱   (SE, 90°)  │
        │         ╲ ╱               │
        │          ╳                │
        │    overlapping detection   │
        │                           │
        └──────────────────────────┘
```

**Шаардлагатай тохиргоо:**
- Камерын байршил (x, y координат)
- Харах чиглэл (0-360°)
- FOV өнцөг (ихэвчлэн 80-110°)
- Reference image + 4 ground control points (image→world mapping)

**Frontend:** Canvas/SVG дээр real-time overlay хийх, detection бүрийг харгалзах камерын өнцгөөр проекцлох.

---

## Хэрэгжүүлэх дараалал

| Алхам | Зүйл | Статус |
|-------|------|--------|
| 1 | IoU-based single-camera object tracking | **Одоо хийж байгаа** |
| 2 | Detection crop export → GPU серверт embedding batch process | Төлөвлөгөө |
| 3 | Redis vector store + cross-camera matching | Төлөвлөгөө |
| 4 | 2D floor plan viewer + FOV overlay | Төлөвлөгөө |
| 5 | 3D reconstruction (тусдаа төсөл, offline only) | Алсын төлөвлөгөө |

---

## BGE-M3-ийн хэрэглэгдэхүүн (тэмдэглэл)

BGE-M3 нь **текст embedding** загвар — зурагнаас шууд embedding гаргаж чадахгүй.

Хэрэв заавал ашиглахыг хүсвэл:
1. Object detection → object crop
2. Crop → VLM (Qwen2-VL) → текст тайлбар: `"silver sedan with roof rails"`
3. Текст тайлбар → BGE-M3 embedding
4. Cross-camera matching — ижил төрлийн машинууд ижил тайлбар → ижил embedding

Гэхдээ энэ нь VLM inference-ийн өртөг өндөр (100-500ms per crop) тул практик биш. Vision Re-ID загвар шууд ашиглах нь илүү тохиромжтой.
