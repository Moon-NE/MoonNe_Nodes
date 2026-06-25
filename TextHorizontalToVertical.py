import os

class TextHorizontalToVertical:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "multiline": True,
                    "default": "123\n456"
                }),
                "enable_convert": ("BOOLEAN", {
                    "default": True
                }),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "convert"
    CATEGORY = "Text/Transform"

    def convert(self, text, enable_convert):
        # 开关关闭时直接返回
        if not enable_convert:
            return (text,)

        if not text:
            return ("",)

        # 按行切分
        lines = text.split("\n")

        # 最长行长度
        max_len = max(len(line) for line in lines)

        # 右侧补全角空格
        padded_lines = [
            line.ljust(max_len, "　")
            for line in lines
        ]

        vertical_lines = []

        # 关键：
        # 日语纵书阅读顺序 = 最下面一行在左边
        # 所以这里要倒序读取行
        for col in range(max_len):
            current_line = [
                padded_lines[row][col]
                for row in reversed(range(len(padded_lines)))
            ]

            vertical_lines.append("".join(current_line))

        result = "\n".join(vertical_lines)
        return (result,)