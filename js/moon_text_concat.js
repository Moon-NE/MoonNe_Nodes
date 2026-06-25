import { app } from "../../scripts/app.js";

app.registerExtension({
    // 扩展名可以改得更通用一些，不仅限于拼接节点
    name: "MoonNodes.DynamicTextInputs",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {

        // 1. 定义一个数组，包含所有需要“无限动态端口”功能的 Python 类名
        const dynamicNodes = [
            "Moon_NE_Text_Concatenate",         // 原本的拼接节点
            "batch_randoml_text"      // 新增的权重随机节点
        ];

        // 2. 只要当前节点的名字在这个数组里，就注入拦截逻辑
        if (dynamicNodes.includes(nodeData.name)) {

            const onConnectionsChange = nodeType.prototype.onConnectionsChange;
            nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info) {
                if (onConnectionsChange) {
                    onConnectionsChange.apply(this, arguments);
                }

                // type === 1 代表 Input（输入端）发生连线变化
                if (type === 1) {
                    const textInputs = this.inputs.filter(inp => inp.name.startsWith("text_"));
                    const lastInput = textInputs[textInputs.length - 1];

                    // 核心逻辑 1：如果最后一个 text 接口被连上了线，自动增加下一个
                    if (lastInput && lastInput.link != null) {
                        // 优化提取序号逻辑：避免断开中间连线导致长度计算错乱产生同名端口
                        const lastIndex = parseInt(lastInput.name.split("_")[1]);
                        this.addInput("text_" + (lastIndex + 1), "STRING");
                    }

                    // 核心逻辑 2：自动清理多余的空接口（保证末尾永远只有 1 个未连线的空接口）
                    for (let i = this.inputs.length - 1; i > 0; i--) {
                        const current = this.inputs[i];
                        const previous = this.inputs[i - 1];

                        if (current.name.startsWith("text_") && previous.name.startsWith("text_")) {
                            if (current.link == null && previous.link == null) {
                                this.removeInput(i);
                            } else {
                                break;
                            }
                        }
                    }
                }
            };
        }
    }
});