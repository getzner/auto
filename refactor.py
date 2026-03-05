import re
import sys

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Pattern 1: Basic endpoints
    # conn = await get_db_conn()
    # try:
    #     ...
    # finally:
    #     await conn.close()
    
    # We will find line numbers and replace manually!
    
    lines = content.split('\n')
    out = []
    
    # Simple state machine
    i = 0
    while i < len(lines):
        # Look for conn = await get_db_conn()
        m1 = re.match(r'^(\s*)conn = await get_db_conn\(\)$', lines[i])
        if m1 and i + 1 < len(lines) and lines[i+1].strip() == "try:":
            indent = m1.group(1)
            # Find the finally block
            j = i + 2
            finally_idx = -1
            except_idx = -1
            for k in range(j, len(lines)):
                if lines[k] == f"{indent}finally:" and k + 1 < len(lines) and lines[k+1].strip() == "await conn.close()":
                    finally_idx = k
                    break
                elif lines[k].startswith(f"{indent}except "):
                    except_idx = k
            
            if finally_idx != -1:
                # We found a full block!
                out.append(f"{indent}from data.db import get_db_session")
                
                # Check if it has an except block. If yes, we need to wrap the whole thing in try...except or let the session exception bubble up.
                # Actually, the user wants us to use get_db_session, which catches DB errors and raises HTTPException(500)
                # So we can just do:
                # async with get_db_session() as conn:
                #    ...
                # And remove try/except/finally completely! (Unless the except block handles something specific, but looking at server.py, they all just return 500 or generic logs).
                
                # Let's be safe. We will write:
                # try:
                #     async with get_db_session() as conn:
                #         ...
                # except Exception as e: ...
                
                if except_idx != -1:
                    out.append(f"{indent}try:")
                    out.append(f"{indent}    async with get_db_session() as conn:")
                    # indent lines from j to except_idx by 4
                    for k in range(j, except_idx):
                        if lines[k].strip():
                            out.append("    " + lines[k])
                        else:
                            out.append(lines[k])
                    # add except block as is
                    for k in range(except_idx, finally_idx):
                        out.append(lines[k])
                else:
                    out.append(f"{indent}async with get_db_session() as conn:")
                    # indent everything between try and finally
                    for k in range(j, finally_idx):
                        if lines[k].strip():
                            out.append("    " + lines[k])
                        else:
                            out.append(lines[k])
                
                i = finally_idx + 2
                continue
                
        # Look for from data.db import get_db_conn followed by conn = await get_db_conn()
        if "from data.db import get_db_conn" in lines[i] and i + 1 < len(lines) and "conn = await get_db_conn()" in lines[i+1] and i+2 < len(lines) and "try:" in lines[i+2]:
            indent = re.match(r'^(\s*)', lines[i+1]).group(1)
            j = i + 3
            finally_idx = -1
            except_idx = -1
            for k in range(j, len(lines)):
                if lines[k] == f"{indent}finally:" and k + 1 < len(lines) and lines[k+1].strip() == "await conn.close()":
                    finally_idx = k
                    break
                elif lines[k].startswith(f"{indent}except "):
                    except_idx = k

            if finally_idx != -1:
                out.append(f"{indent}from data.db import get_db_session")
                if except_idx != -1:
                    out.append(f"{indent}try:")
                    out.append(f"{indent}    async with get_db_session() as conn:")
                    # indent lines from j to except_idx by 4
                    for k in range(j, except_idx):
                        if lines[k].strip():
                            out.append("    " + lines[k])
                        else:
                            out.append(lines[k])
                    # add except block as is
                    for k in range(except_idx, finally_idx):
                        out.append(lines[k])
                else:
                    out.append(f"{indent}async with get_db_session() as conn:")
                    # indent everything between try and finally
                    for k in range(j, finally_idx):
                        if lines[k].strip():
                            out.append("    " + lines[k])
                        else:
                            out.append(lines[k])
                i = finally_idx + 2
                continue
        
        # Health check specific replacement
        if "conn = await get_db_conn()" in lines[i] and lines[i-1].strip() == "try:":
            # Wait, health check is:
            # try:
            #     conn = await get_db_conn()
            #     await conn.fetchval("SELECT 1")
            #     await conn.close()
            #     services["postgres"] = "ok"
            # except Exception as e:
            if i + 3 < len(lines) and "await conn.close()" in lines[i+2]:
                indent = re.match(r'^(\s*)', lines[i]).group(1)
                out.pop() # remove try:
                # We will keep the try from original
                out.append(f"{indent[:-4]}try:")
                out.append(f"{indent}from data.db import get_db_session")
                out.append(f"{indent}async with get_db_session(timeout=3.0) as conn:")
                out.append(f"{indent}    await conn.fetchval(\"SELECT 1\")")
                out.append(f"{indent}services[\"postgres\"] = \"ok\"")
                i += 4
                continue

        out.append(lines[i])
        i += 1
        
    with open(filepath, 'w') as f:
        f.write("\n".join(out))
    print(f"Refactored {filepath}")

import glob
process_file("api/server.py")
process_file("data/cost_tracker.py")

