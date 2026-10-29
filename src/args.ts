export function option(args: string[], name: string, required = false) {
  const index = args.indexOf(name);
  const value = index >= 0 ? args[index + 1] : undefined;
  if (required && !value) throw new Error(`${name} is required`);
  return value;
}

export function options(args: string[], name: string) {
  const values: string[] = [];
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === name && args[index + 1] && !args[index + 1].startsWith("-")) values.push(args[index + 1]);
  }
  return values;
}

export function optionList(args: string[], name: string) {
  const index = args.indexOf(name);
  if (index < 0) return [];
  const values: string[] = [];
  for (let cursor = index + 1; cursor < args.length && !args[cursor].startsWith("-"); cursor += 1) values.push(args[cursor]);
  return values;
}

export function flag(args: string[], name: string) { return args.includes(name); }

export function stripOptions(args: string[], names: string[]) {
  const remove = new Set(names);
  const out: string[] = [];
  for (let index = 0; index < args.length; index += 1) {
    if (remove.has(args[index])) { index += 1; continue; }
    out.push(args[index]);
  }
  return out;
}

export function positionals(args: string[]) {
  const out: string[] = [];
  for (let index = 0; index < args.length; index += 1) {
    if (args[index].startsWith("--")) {
      if (!["--pretty", "--reverse", "--scheduled", "--install-scheduler"].includes(args[index])) index += 1;
    } else out.push(args[index]);
  }
  return out;
}
