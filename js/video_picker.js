import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "NTD11.VideoPicker",
    nodeCreated(node) {
        if (node.comfyClass !== "NTD11VideoFile") return;
        const video = node.widgets.find((widget) => widget.name === "video");
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".mp4,.mkv,.webm,.mov,.m4v,.avi";
        input.style.display = "none";
        document.body.append(input);
        let uploading = false;
        const button = node.addWidget("button", "Choose video file...", null, () => {
            if (uploading) return;
            input.value = "";
            app.canvas.node_widget = null;
            input.click();
        });
        button.options.serialize = false;
        input.onchange = async () => {
            const file = input.files?.[0];
            if (!file || uploading) return;
            if (!/\.(mp4|mkv|webm|mov|m4v|avi)$/i.test(file.name)) {
                alert("Choose an MP4, MKV, WebM, MOV, M4V, or AVI video.");
                return;
            }
            uploading = true;
            button.label = "Preparing video...";
            node.setDirtyCanvas(true, true);
            try {
                const data = new FormData();
                data.append("image", file);
                data.append("type", "input");
                data.append("subfolder", "ntd11_videos");
                const response = await api.fetchApi("/upload/image", { method: "POST", body: data });
                if (!response.ok) throw new Error(`Could not prepare video (${response.status})`);
                const result = await response.json();
                const path = result.subfolder ? `${result.subfolder}/${result.name}` : result.name;
                if (!video.options.values.includes(path)) video.options.values.push(path);
                video.value = path;
                video.callback?.(path);
            } catch (error) {
                alert(error.message || String(error));
            } finally {
                uploading = false;
                button.label = "Choose video file...";
                node.setDirtyCanvas(true, true);
            }
        };
        const onRemoved = node.onRemoved;
        node.onRemoved = function (...args) {
            input.remove();
            return onRemoved?.apply(this, args);
        };
    },
});
