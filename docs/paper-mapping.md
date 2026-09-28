# Papers → this POC

Two papers frame the project. Neither was reproduced. The table separates what each paper reports from what this
repository actually implements and measures.

## 1. Donut — historical background

**Geewook Kim, Teakgyu Hong, Moonbin Yim, Jeongyeon Nam, Jinyoung Park, Jinyeong Yim, Wonseok Hwang, Sangdoo Yun,
Dongyoon Han, Seunghyun Park.** *OCR-free Document Understanding Transformer.* arXiv:2111.15664, first posted
30 Nov 2021; ECCV 2022. <https://arxiv.org/abs/2111.15664>

What the abstract says: visual document understanding systems usually hand the reading step to an off-the-shelf OCR
engine, which brings computational cost, inflexibility across languages and document types, and **OCR error
propagation** into the later steps. Donut is a Transformer trained to go from the document image straight to
structured output, with no OCR stage, and was reported as state of the art in both speed and accuracy on several
document understanding tasks at the time. The authors also released a synthetic document generator for pre-training.

How it motivates this POC: Donut is the early, well-known argument that the OCR stage can be removed. Our direct path
follows that idea (image in, fields out) but uses a general-purpose vision-language model, **not Donut**, which is a
specialised, fine-tuned architecture. We did not train, run or evaluate Donut. Our synthetic receipt generator is our
own and is unrelated to Donut's SynthDoG.

## 2. OCR or Not? — primary research basis

**Jiyuan Shen, Peiyue Yuan, Atin Ghosh, Yifan Mai, Daniel Dahlmeier.** *OCR or Not? Rethinking Document Information
Extraction in the MLLMs Era with Real-World Large-Scale Datasets.* arXiv:2603.02789, 3 Mar 2026.
<https://arxiv.org/abs/2603.02789>

What the paper reports (from its abstract and body):

- It asks whether an MLLM-only pipeline can match an OCR + MLLM pipeline for business-document information extraction.
- It compares three input settings: **OCR-extracted text only, raw document images only, and both combined**.
- It uses the authors' **internal** datasets of real business documents (supply-chain and finance domains:
  multilingual, with nested line items and heterogeneous headers), a proprietary in-house OCR engine, and a range of
  proprietary and open MLLMs.
- It scores key–value predictions with precision, recall and F1.
- It proposes an automated, LLM-based hierarchical **error analysis** framework.
- It concludes that "OCR may not be necessary for powerful MLLMs, as image-only input can achieve comparable
  performance to OCR-enhanced approaches," and that careful schema, exemplars and instructions improve results.

## What our experiment represents, and what it does not

| Aspect | The 2026 paper | This POC |
|---|---|---|
| Question | Image-only vs OCR-assisted input for document information extraction | **Same question**, one document type |
| Input settings | OCR text only · image only · image + OCR | OCR text only (our "OCR-assisted" path) · image only (our "direct" path). **Image + OCR is not tested.** |
| Holding the model fixed | Each MLLM evaluated under each input setting | One model (Qwen3-VL 4B Instruct, local) under both settings |
| Documents | Large real-world internal business datasets, multilingual | **30 synthetic English receipts**, 5 layouts × 6 image conditions |
| OCR | Proprietary in-house engine | RapidOCR (open PP-OCR models) on CPU, with our own line rebuilding |
| Models | Large proprietary MLLMs and open models, via APIs | One 4.4 B-parameter open model, quantised, on a laptop iGPU |
| Schema | Header fields and nested line items | 6 flat header fields; no line items |
| Metric | Key–value precision / recall / F1 | Field accuracy (primary) plus key–value P/R/F1 in the same spirit; per-field outcomes |
| Error analysis | Automated LLM-based hierarchical framework | **Manual** reading of every error, plus whether our review signals flagged it |
| Prompt study | Schema, exemplars and instruction refinements | One fixed prompt, fixed before evaluation; not studied |
| Human review | Not part of the study | Part of the app: every extraction is a draft until a person approves it |

**Therefore:** our numbers are a small, single-model, synthetic-data probe of the paper's question on one machine.
They cannot confirm or contradict the paper's findings, which concern large models on large real datasets. The
paper's results, datasets, OCR engine and models were not reproduced.

**Original to this project:** the synthetic receipt set and its generator, the fixed-model two-path comparison, the
review signals (validation rules and cross-path disagreement) and their measured coverage of errors, and the local
review → approval → export workflow.
