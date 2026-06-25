class ContainsAnyDict(dict):
    def __contains__(self, key):
        return True

    def __getitem__(self, key):
        # 核心修复 1：拦截字典取值
        # 如果是原本就有的键（text_0），正常返回它；
        # 如果是前端动态生成的键（text_1, text_2），伪造一个数据类型返回给 ComfyUI 后端骗过验证。
        return super().get(key, ("STRING", {"forceInput": True}))


class Moon_NE_Text_Concatenate:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "delimiter": ("STRING", {"default": ", "}),
                "clean_whitespace": (["true", "false"],),
            },
            "optional": ContainsAnyDict({
                # 初始只保留一个 text_0，剩下的全靠前端 JS 动态追加
                "text_0": ("STRING", {"forceInput": True}),
            })
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "text_concatenate"
    CATEGORY = "Moon_Nodes/Text"

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        # 核心修复 2：必须使用 **kwargs 接收 ComfyUI 丢过来的所有连线参数
        return True

    def text_concatenate(self, delimiter, clean_whitespace, **kwargs):
        if delimiter in ("\n", "\\n"):
            delimiter = "\n"

        text_inputs = []

        # 过滤并排序所有输入的键（例如 text_0, text_1, text_2...）
        sorted_keys = sorted(
            kwargs.keys(),
            key=lambda x: int(x.split("_")[1]) if "_" in x and x.split("_")[1].isdigit() else 0
        )

        for k in sorted_keys:
            v = kwargs[k]

            if isinstance(v, str):
                if clean_whitespace == "true":
                    v = v.strip()

                if v != "":
                    text_inputs.append(v)

        merged_text = delimiter.join(text_inputs)

        return (merged_text,)