# ComfyUI One-Click Random Generator Nodes

A set of ComfyUI custom nodes designed for ultimate laziness. Generate diverse images with a single click using randomized prompts and dynamic weights.

## 🚀 Key Features

* **Probabilistic Prompts:** Set custom probability thresholds for specific keywords/prompts to appear.
* **Randomized Weights:** Automatically assign randomized weights to prompts within your preferred range to discover unexpected variations.

## Usage
Honestly, I'm too lazy to write a detailed guide, and let's be real—nobody actually opens the README to read it anyway. Just plug it into your workflow and figure it out. It's not rocket science. Enjoy!


Batch Conditional Text
🇨🇳 中文说明 (Chinese)
这是一个专门用于 ComfyUI 批次生成（如动画、视频帧或多图批量生成）的条件文本节点。它可以根据当前批次索引（Batch Index）在指定的范围内、范围外或特定点，按设定的概率输出指定的文本。

📌 核心功能
双区间模式自动切换：

当 greater_than 小于 less_than 时 ➡️ 触发区间内模式（如：在 25 到 40 之间）。

当 greater_than 大于 less_than 时 ➡️ 触发区间外模式（如：小于 25 或大于 40）。

当两者相等时 ➡️ 触发单点模式（如：刚好等于 40）。

独立随机率：支持通过 probability (0.0 - 1.0) 调整触发概率。由于结合了 seed 和 batch_index，每个批次帧的随机结果都是独立且可复现的。

原生防缓存：内置 IS_CHANGED 机制，确保连续生成时概率判断每次都生效，不会被 ComfyUI 缓存锁死。

※新增权重范围内随机功能

💬 示例配置
例子 1（区间外）： 批次小于 25 或大于 40 时，有 30% 概率输出 good day。

greater_than: 40

less_than: 25

probability: 0.30

text: good day

例子 2（区间内）： 批次在 25 到 40 之间时，有 50% 概率输出 bad day。

greater_than: 25

less_than: 40

probability: 0.50

text: bad day
English Guide
This is a conditional text node designed for ComfyUI batch processing (e.g., animations, video frames, or batch image generation). It outputs a specified text based on whether the current batch_index meets the range conditions, under a custom execution probability.

📌 Key Features
Auto-Switching Range Modes:

If greater_than < less_than ➡️ Inside Range mode (e.g., between 25 and 40).

If greater_than > less_than ➡️ Outside Range mode (e.g., less than 25 OR greater than 40).

If they are equal ➡️ Single Point mode (e.g., exactly equal to 40).

Independent Probability: Adjust the trigger rate via probability (0.0 - 1.0). By combining seed and batch_index, the randomness for each frame remains unique yet perfectly reproducible.

Cache Busting: Built-in IS_CHANGED mechanism ensures ComfyUI evaluates the probability on every single run instead of frozen by cache.

💬 Examples
Ex 1 (Outside Range): Output good day with a 30% chance when batch is less than 25 or greater than 40.

greater_than: 40, less_than: 25, probability: 0.30, text: good day

Ex 2 (Inside Range): Output bad day with a 50% chance when batch is between 25 and 40.

greater_than: 25, less_than: 40, probability: 0.50, text: bad day

※Newly added random weight within order range

日本語ガイド (Japanese)
このノードは、ComfyUIのバッチ処理（アニメーション、ビデオフレーム、複数画像の連続生成など）向けに設計された条件付きテキスト出力ノードです。現在の batch_index が指定された条件を満たしている場合、設定された確率に基づいてテキストを出力します。

📌 主な機能
範囲モードの自動切り替え:

greater_than < less_than の場合 ➡️ 範囲内モード（例: 25から40の間）。

greater_than > less_than の場合 ➡️ 範囲外モード（例: 25未満、または40より大きい）。

両者が同じ場合 ➡️ ピンポイントモード（例: ちょうど40の時）。

独立した確率設定: probability (0.0 - 1.0) で出力確率をコントロール。seed と batch_index を組み合わせているため、各フレームのランダム性は独立しつつ、再現性も確保されます。

キャッシュ対策: IS_CHANGED を実装しているため、ComfyUIのキャッシュによって確率計算がスキップされることなく、毎回の実行で正しく判定されます。

💬 設定例
例 1（範囲外）: バッチが25未満、または40より大きい時に30%の確率で good day を出力する。

greater_than: 40, less_than: 25, probability: 0.30, text: good day

例 2（範囲内）: バッチが25から40の間の時に50%の確率で bad day を出力する。

greater_than: 25, less_than: 40, probability: 0.50, text: bad day
