declare module "@alicloud/log" {
  const Client: new (options: Record<string, unknown>) => { getLogs(project: string, logstore: string, from: Date, to: Date, query: Record<string, unknown>): Promise<any> };
  export default Client;
}
