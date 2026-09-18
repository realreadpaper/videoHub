import json,sys
w=json.load(open(sys.argv[1]))
nodes={n["id"]:n for n in w["nodes"]}
print("=== 全节点 (id | type | 输出->去处) ===")
# 构建连接索引
links={}
for l in w.get("links",[]):
    # [link_id, origin_id, origin_slot, target_id, target_slot, type]
    links.setdefault(l[1],[]).append((l[2], l[3], l[4], l[5]))
for nid in sorted(nodes):
    n=nodes[nid]
    t=n.get("type","?")
    wv=n.get("widgets_values")
    out=[]
    for (oslot,tid,tslot,ttype) in links.get(nid,[]):
        out.append("out%d->#%d.%d(%s)"%(oslot,tid,tslot,ttype))
    inps=[]
    for i in n.get("inputs",[]) or []:
        lk=i.get("link")
        src=""
        if lk is not None:
            for l in w.get("links",[]):
                if l[0]==lk: src="<-#%d.%d"%(l[1],l[2])
        inps.append("%s%s"%(i.get("name"),src))
    print("#%-4d %-48s in:[%s] out:[%s]" % (nid,t,",".join(inps),",".join(out)))
    if wv: print("        widgets:",str(wv)[:130])
