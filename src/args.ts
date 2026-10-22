export function option(args:string[],name:string,required=false){const index=args.indexOf(name);const value=index>=0?args[index+1]:undefined;if(required&&!value)throw new Error(`${name} is required`);return value}
export function flag(args:string[],name:string){return args.includes(name)}
export function positionals(args:string[]){const out:string[]=[];for(let i=0;i<args.length;i++){if(args[i].startsWith("--")){if(!["--pretty","--reverse","--scheduled","--install-scheduler"].includes(args[i]))i++;}else out.push(args[i]);}return out}
