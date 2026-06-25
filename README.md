# ComfyUI One-Click Random Generator Nodes

A set of ComfyUI custom nodes designed for ultimate laziness. Generate diverse images with a single click using randomized prompts and dynamic weights.

## 🚀 Key Features

* **Probabilistic Prompts:** Set custom probability thresholds for specific keywords/prompts to appear.
* **Randomized Weights:** Automatically assign randomized weights to prompts within your preferred range to discover unexpected variations.

## Usage
Honestly, I'm too lazy to write a detailed guide, and let's be real—nobody actually opens the README to read it anyway. Just plug it into your workflow and figure it out. It's not rocket science. Enjoy!


## Batch Conditional Text Weight

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


## batch randoml text
Allows you to input multiple text strings and select one randomly based on a custom weight ratio (e.g., inputting weights `1, 2, 3` gives the third text the highest probability of being chosen).
Fault Tolerance: Automatically handles mismatched weight counts and invalid weight inputs.


