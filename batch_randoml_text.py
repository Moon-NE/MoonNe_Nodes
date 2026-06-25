import random

class ContainsAnyDict(dict):
    def __contains__(self, key):
        return True

    def __getitem__(self, key):
        # 拦截字典取值，骗过 ComfyUI 后端验证
        return super().get(key, ("STRING", {"forceInput": True}))


class batch_randoml_text:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # 输入权重，默认 1,1,1
                "weights": ("STRING", {"default": "1, 1, 1"}),
                # 必须加入 seed，将其设置为 randomize，以强制 ComfyUI 每次运行都刷新该节点
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
            "optional": ContainsAnyDict({
                # 初始只保留一个 text_0，剩下的全靠前端 JS 动态追加
                "text_0": ("STRING", {"forceInput": True}),
            })
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "text_weighted_random"
    CATEGORY = "Moon_Nodes/Text"

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        # 必须使用 **kwargs 接收丢过来的所有连线参数
        return True

    def text_weighted_random(self, weights, seed, **kwargs):
        text_inputs = []

        # 过滤并排序所有输入的键（提取所有 text_ 开头的输入）
        sorted_keys = sorted(
            [k for k in kwargs.keys() if k.startswith("text_")],
            key=lambda x: int(x.split("_")[1]) if "_" in x and x.split("_")[1].isdigit() else 0
        )

        # 收集有效的文本输入
        for k in sorted_keys:
            v = kwargs[k]
            if isinstance(v, str) and v.strip() != "":
                text_inputs.append(v)

        # 如果没有任何有效文本输入，返回空字符串
        if not text_inputs:
            return ("",)

        # 解析权重输入："1, 2, 3" -> [1.0, 2.0, 3.0]
        weight_list = []
        for w in weights.split(","):
            try:
                weight_list.append(float(w.strip()))
            except ValueError:
                # 容错处理：如果用户不小心输入了字母或多余的符号，默认该项权重为 1.0
                weight_list.append(1.0)

        # 长度对齐处理：防止输入的文本数量和权重数量不一致
        if len(weight_list) < len(text_inputs):
            # 如果权重填少了（比如 4 个 text 但只有 3 个权重），缺少的自动用 1.0 补齐
            weight_list.extend([1.0] * (len(text_inputs) - len(weight_list)))
        elif len(weight_list) > len(text_inputs):
            # 如果权重填多了，截断多余的权重
            weight_list = weight_list[:len(text_inputs)]

        # 根据种子初始化随机状态（保证 ComfyUI 可以在固定 seed 下重现同样的随机结果）
        random.seed(seed)
        
        # random.choices 根据给定的权重列表进行随机选择，k=1 表示只选出一个
        selected_text = random.choices(text_inputs, weights=weight_list, k=1)[0]

        return (selected_text,)