---
title: Action Camera & Accessories Compliance Decision Guide
jurisdiction: US, EU
authority: 综合（各文档分列）
source: internal
category: action-camera
review_status: draft
---

# Action Camera & Accessories Compliance Decision Guide

> ⚠️ draft：内容按法规公共知识整理，正式使用前必须对照各专项文档与官方来源核验。
> 本文是"品类 → 适用规则"的决策索引（category-to-rules index）：查某类配件要什么认证，先看这张表，再跳到对应专项文档。

## Category Decision Table

| Category | US | EU | Key docs |
|---|---|---|---|
| Action camera with Wi-Fi/BT/GPS (e.g. GoPro, Insta360, DJI Osmo Action) | FCC certification (Part 15 intentional radiator, FCC ID) | RED + EMC + RoHS (CE); EN 300 328 / 62368-1 / 55032 | FCC doc, EU electronics CE doc |
| Selfie stick / tripod, purely mechanical (no electronics) 自拍杆·三脚架（纯机械） | No mandatory certification; CPSC general safety + California Prop 65 | NO CE directive applies — must NOT be CE marked; GPSR general safety + REACH | GPSR, Prop 65 docs |
| Selfie stick with Bluetooth remote / electronic shutter 蓝牙遥控自拍杆 | FCC (radio module) | RED + EMC + RoHS; built-in battery adds battery rules | EU electronics CE, battery docs |
| Protective lens / filter, tempered glass or acrylic 保护镜·滤镜 | CPSC general safety (shatter risk) + Prop 65 (adhesives, coatings) | GPSR + REACH; no CE | GPSR, REACH docs |
| Camera housing / protective case (TPU/PC) 保护壳 | Prop 65 (phthalates, lead) | GPSR + REACH; no CE | GPSR, Prop 65 |
| Charger / power adapter 充电器·电源适配器 | FCC DoC or verification + de-facto NRTL (UL/ETL 62368-1, Amazon requires) | LVD + EMC + RoHS (CE) | EU electronics CE, battery/marketplace docs |
| Spare lithium-ion battery 备用锂电池 | UN 38.3 + IEC 62133-2 (transport & platform) | Batteries Regulation CE + transport rules; WEEE | battery docs |
| Mounts / adhesive bases / helmet mount 支架·底座 | None mandatory; must NOT claim protective/safety function (avoid PPE) | Same (PPE regulation not applicable but marketing claims may trigger it) | — |
| Fabric wrist strap / lanyard 织物腕带·挂带 | Prop 65 (azo dyes, lead) | REACH (azo dyes, Annex XVII entry 43) + GPSR | REACH doc |
| Memory card (SD/microSD) 存储卡 | FCC Part 15 subpart B (unintentional radiator, verification/DoC) | RoHS + EMC | FCC, RoHS docs |

## Three Common Pitfalls

1. **CE-marking purely mechanical accessories**: selfie sticks, lens protectors, mechanical tripods fall under NO CE legislation — affixing CE is itself a violation (see CE doc "常见踩坑").
2. **Selling helmet mounts as protective gear**: an action-camera helmet mount is not personal protective equipment (PPE); ad wording like "safety protection / impact resistant" can trigger PPE Regulation (EU) 2016/425 or US CPSC helmet standard (16 CFR 1203) disputes — market it only as "mount / fix / attach".
3. **FCC ID from the module alone**: a Wi-Fi camera must be certified in its final form (antenna + housing); a pre-certified module's grant does not automatically transfer (see FCC doc).

## Battery Shipping Checklist (the most common seizure point for China→US/EU shipments) 含电池设备发货清单

- UN 38.3 test summary (request from the battery manufacturer)
- Equipment with installed battery ships as UN 3481 PI 967; spare batteries packed with it as PI 966
- Terminals insulated, batteries in individual plastic bags, lithium battery mark on the outer box
- Batteries ≤100 Wh get simplified rules (most action-camera batteries are 5–20 Wh)
- Marketplaces (Amazon) additionally require MSDS + IEC 62133-2 / UL 2054 reports

## Marketplace Document Checklist (Amazon)

| Market | What they ask for |
|---|---|
| Amazon US | FCC ID documents; battery products UN38.3 + IEC 62133-2; chargers NRTL report; Prop 65 declarations for flagged listings |
| Amazon EU | CE DoC + test reports (RED/EMC/LVD/RoHS); WEEE registration number (DE); LUCID (DE); French IDU; GPSR responsible person; battery regulation label photos |
