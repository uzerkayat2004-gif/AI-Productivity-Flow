# Notebook Sketch Remotion proof of concept

This isolated composition tests whether Video Flow can reproduce a warm,
hand-drawn editorial explainer language with deterministic Remotion primitives.

It intentionally does not modify the production `VideoFlow` composition.

Render from `video_flow_renderer`:

```powershell
npx remotion render src/notebook-sketch-poc/index.ts NotebookSketchPoC out/notebook-sketch-poc.mp4 --codec=h264 --crf=18
```

The proof covers six reusable scene families: title, workflow, hero metric,
comparison, quotation, and closing verdict.
