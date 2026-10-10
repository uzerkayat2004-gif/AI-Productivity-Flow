import type {FrameExpression, SemanticAnchor, Scalar} from "./schema";

export type FrameRuntime = {
  frame: number;
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  anchors: Record<string, {start: number; end: number; center: number; progress: number}>;
};

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

export const ease = (value: number, kind: "linear" | "easeIn" | "easeOut" | "easeInOut" = "linear") => {
  const t = clamp01(value);
  if (kind === "easeIn") return t * t;
  if (kind === "easeOut") return 1 - (1 - t) * (1 - t);
  if (kind === "easeInOut") return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  return t;
};

const numeric = (value: unknown, fallback = 0) => {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

/** A tiny, deliberately safe arithmetic parser for string expressions. */
class ExpressionParser {
  private index = 0;
  private readonly tokens: string[];

  constructor(source: string, private readonly variables: Record<string, number>) {
    this.tokens = source
      .replace(/\s+/g, "")
      .match(/(?:\d*\.\d+|\d+\.?\d*|[A-Za-z_$][\w$]*|\*\*|[()+\-*/%,])/g) ?? [];
  }

  parse() {
    if (this.tokens.length === 0) return Number.NaN;
    const value = this.additive();
    return this.index === this.tokens.length ? value : Number.NaN;
  }

  private peek() { return this.tokens[this.index]; }
  private take(expected?: string) {
    const token = this.tokens[this.index];
    if (expected && token !== expected) return undefined;
    this.index += 1;
    return token;
  }

  private additive(): number {
    let value = this.multiplicative();
    while (this.peek() === "+" || this.peek() === "-") {
      const operator = this.take();
      const rhs = this.multiplicative();
      value = operator === "+" ? value + rhs : value - rhs;
    }
    return value;
  }

  private multiplicative(): number {
    let value = this.power();
    while (["*", "/", "%"].includes(this.peek() ?? "")) {
      const operator = this.take();
      const rhs = this.power();
      if (operator === "*") value *= rhs;
      else if (operator === "/") value = rhs === 0 ? 0 : value / rhs;
      else value = rhs === 0 ? 0 : value % rhs;
    }
    return value;
  }

  private power(): number {
    let value = this.unary();
    if (this.take("**")) value = Math.pow(value, this.unary());
    return value;
  }

  private unary(): number {
    if (this.take("+")) return this.unary();
    if (this.take("-")) return -this.unary();
    return this.primary();
  }

  private primary(): number {
    const token = this.peek();
    if (token === "(") {
      this.take();
      const value = this.additive();
      this.take(")");
      return value;
    }
    if (!token) return Number.NaN;
    if (/^(?:\d*\.\d+|\d+\.?\d*)$/.test(token)) {
      this.take();
      return numeric(token, Number.NaN);
    }
    if (/^[A-Za-z_$]/.test(token)) {
      this.take();
      if (this.take("(") !== undefined) {
        const args: number[] = [];
        if (this.peek() !== ")") {
          while (true) {
            args.push(this.additive());
            if (this.take(",") === undefined) break;
          }
        }
        this.take(")");
        return callFunction(token, args);
      }
      return this.variables[token] ?? Number.NaN;
    }
    this.take();
    return Number.NaN;
  }
}

const callFunction = (name: string, args: number[]) => {
  switch (name) {
    case "sin": return Math.sin(args[0] ?? 0);
    case "cos": return Math.cos(args[0] ?? 0);
    case "tan": return Math.tan(args[0] ?? 0);
    case "abs": return Math.abs(args[0] ?? 0);
    case "sqrt": return Math.sqrt(Math.max(0, args[0] ?? 0));
    case "floor": return Math.floor(args[0] ?? 0);
    case "ceil": return Math.ceil(args[0] ?? 0);
    case "round": return Math.round(args[0] ?? 0);
    case "min": return Math.min(...args);
    case "max": return Math.max(...args);
    case "clamp": return Math.max(args[1] ?? 0, Math.min(args[2] ?? 1, args[0] ?? 0));
    case "lerp": return (args[0] ?? 0) + ((args[1] ?? 0) - (args[0] ?? 0)) * (args[2] ?? 0);
    case "smoothstep": {
      const t = clamp01(args[0] ?? 0);
      return t * t * (3 - 2 * t);
    }
    default: return Number.NaN;
  }
};

const looksLikeExpression = (value: string) =>
  /(?:^|[\s(])(?:frame|fps|width|height|duration|t|pi)(?:$|[\s),+\-*/%])/.test(value)
  || /[+\-*/%(),]/.test(value)
  || /^-?(?:\d*\.\d+|\d+\.?\d*)$/.test(value.trim());

export const evaluateStringExpression = (source: string, runtime: FrameRuntime): number | string => {
  if (!looksLikeExpression(source)) return source;
  const parsed = new ExpressionParser(source, {
    frame: runtime.frame,
    fps: runtime.fps,
    width: runtime.width,
    height: runtime.height,
    duration: runtime.durationInFrames,
    t: runtime.fps > 0 ? runtime.frame / runtime.fps : 0,
    progress: runtime.durationInFrames > 0 ? runtime.frame / runtime.durationInFrames : 0,
    pi: Math.PI,
  }).parse();
  return Number.isFinite(parsed) ? parsed : source;
};

const anchorTable = (anchors: SemanticAnchor[] | undefined, runtime: Omit<FrameRuntime, "anchors">) => {
  const table: FrameRuntime["anchors"] = {};
  for (const anchor of anchors ?? []) {
    const start = numeric(resolveFrameExpression(anchor.start, {...runtime, anchors: table}), 0);
    const end = Math.max(start, numeric(anchor.end === undefined ? start : resolveFrameExpression(anchor.end, {...runtime, anchors: table}), start));
    const progress = end === start ? (runtime.frame >= start ? 1 : 0) : clamp01((runtime.frame - start) / (end - start));
    table[anchor.id] = {start, end, center: start + (end - start) / 2, progress};
  }
  return table;
};

export const runtimeFor = (frame: number, options: Omit<FrameRuntime, "frame" | "anchors">, anchors?: SemanticAnchor[]): FrameRuntime => {
  const base = {...options, frame};
  return {...base, anchors: anchorTable(anchors, base)};
};

export const resolveFrameExpression = (expression: FrameExpression, runtime: FrameRuntime): number | string => {
  if (typeof expression === "number") return Number.isFinite(expression) ? expression : 0;
  if (typeof expression === "string") return evaluateStringExpression(expression, runtime);
  // Manifests arrive over JSON and can contain null or malformed expressions.
  // Treat those values as a deterministic zero rather than crashing a render.
  if (!expression || typeof expression !== "object") return 0;
  if ("value" in expression && !("op" in expression)) return resolveFrameExpression(expression.value, runtime);
  const operation = expression as Extract<FrameExpression, {op: string}>;
  switch (operation.op) {
    case "add": return numeric(resolveFrameExpression(operation.left, runtime)) + numeric(resolveFrameExpression(operation.right, runtime));
    case "sub": return numeric(resolveFrameExpression(operation.left, runtime)) - numeric(resolveFrameExpression(operation.right, runtime));
    case "mul": return numeric(resolveFrameExpression(operation.left, runtime)) * numeric(resolveFrameExpression(operation.right, runtime));
    case "div": {
      const denominator = numeric(resolveFrameExpression(operation.right, runtime));
      return denominator === 0 ? 0 : numeric(resolveFrameExpression(operation.left, runtime)) / denominator;
    }
    case "mod": {
      const denominator = numeric(resolveFrameExpression(operation.right, runtime));
      return denominator === 0 ? 0 : numeric(resolveFrameExpression(operation.left, runtime)) % denominator;
    }
    case "pow": return Math.pow(numeric(resolveFrameExpression(operation.left, runtime)), numeric(resolveFrameExpression(operation.right, runtime)));
    case "min": return Math.min(...operation.values.map((item: FrameExpression) => numeric(resolveFrameExpression(item, runtime))));
    case "max": return Math.max(...operation.values.map((item: FrameExpression) => numeric(resolveFrameExpression(item, runtime))));
    case "clamp": return Math.max(numeric(resolveFrameExpression(operation.min, runtime)), Math.min(numeric(resolveFrameExpression(operation.max, runtime)), numeric(resolveFrameExpression(operation.value, runtime))));
    case "lerp": return numeric(resolveFrameExpression(operation.from, runtime)) + (numeric(resolveFrameExpression(operation.to, runtime)) - numeric(resolveFrameExpression(operation.from, runtime))) * numeric(resolveFrameExpression(operation.progress, runtime));
    case "sin": return Math.sin(numeric(resolveFrameExpression(operation.value, runtime)));
    case "cos": return Math.cos(numeric(resolveFrameExpression(operation.value, runtime)));
    case "tan": return Math.tan(numeric(resolveFrameExpression(operation.value, runtime)));
    case "abs": return Math.abs(numeric(resolveFrameExpression(operation.value, runtime)));
    case "sqrt": return Math.sqrt(Math.max(0, numeric(resolveFrameExpression(operation.value, runtime))));
    case "floor": return Math.floor(numeric(resolveFrameExpression(operation.value, runtime)));
    case "ceil": return Math.ceil(numeric(resolveFrameExpression(operation.value, runtime)));
    case "round": return Math.round(numeric(resolveFrameExpression(operation.value, runtime)));
    case "smoothstep": return ease(numeric(resolveFrameExpression(operation.value, runtime)), "easeInOut");
    case "interpolate": {
      const input = numeric(resolveFrameExpression(operation.input, runtime));
      const inputs = operation.inputRange;
      const outputs = operation.outputRange;
      if (inputs.length < 2 || outputs.length < 2 || inputs.length !== outputs.length) return outputs[0] ?? 0;
      const first = inputs.findIndex((item) => input <= item);
      const index = first < 0 ? inputs.length - 2 : Math.max(0, first - 1);
      const left = inputs[index] ?? inputs[0];
      const right = inputs[index + 1] ?? inputs[inputs.length - 1];
      const progress = right === left ? 1 : clamp01((input - left) / (right - left));
      return (outputs[index] ?? outputs[0]) + ((outputs[index + 1] ?? outputs[outputs.length - 1]) - (outputs[index] ?? outputs[0])) * progress;
    }
    case "spring": {
      const springFrame = operation.frame === undefined ? runtime.frame : numeric(resolveFrameExpression(operation.frame, runtime));
      const duration = Math.max(1, operation.duration ?? runtime.fps);
      const t = clamp01(springFrame / duration);
      const stiffness = Math.max(1, operation.stiffness ?? 10);
      const damping = Math.max(0.01, operation.damping ?? 0.8);
      const natural = 1 - Math.exp(-stiffness * t * damping) * Math.cos(stiffness * t);
      return (operation.from ?? 0) + ((operation.to ?? 1) - (operation.from ?? 0)) * clamp01(natural);
    }
    case "anchor": {
      const anchor = runtime.anchors[operation.id];
      if (!anchor) return 0;
      return anchor[operation.field ?? "start"];
    }
    default: return 0;
  }
};

export const resolveScalar = <T extends Scalar>(value: T | undefined, runtime: FrameRuntime, fallback = 0): number | string => {
  if (value === undefined) return fallback;
  return resolveFrameExpression(value, runtime);
};

export const toNumber = (value: unknown, fallback = 0) => numeric(value, fallback);
export const clamp = (value: number, min = 0, max = 1) => Math.max(min, Math.min(max, value));

