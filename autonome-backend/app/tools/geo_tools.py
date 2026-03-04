import json
try:
    from Bio import Entrez
except ImportError:
    Entrez = None
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from sqlmodel import Session, select

from app.core.database import engine
from app.core.logger import log
from app.models.domain import PublicDataset

# ⚠️ 必须配置 Email 才能使用 NCBI 的 API
if Entrez:
    Entrez.email = "autonome_agent@example.com"
from Bio import Entrez
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from sqlmodel import Session, select

from app.core.database import engine
from app.core.logger import log
from app.models.domain import PublicDataset

# ⚠️ 必须配置 Email 才能使用 NCBI 的 API
Entrez.email = "autonome_agent@example.com" 

@tool
def search_and_vectorize_geo_data(query: str, user_id: int) -> str:
    """
    当用户请求查询或寻找某些疾病、药物（如肺癌 TKI 耐药）的公共测序/单细胞数据时，必须调用此工具。
    工具会自动检索 NCBI GEO 数据库，提取元数据，将其向量化（Embedding）并存入本地数据库。
    """
    log.info(f"🔍 Agent 触发了 GEO 检索任务: {query}, User ID: {user_id}")
    
    try:
        # 1. 调用 NCBI E-utilities 搜索 GEO Series (GSE) 数据集
        # 限定返回前 3 个最高相关的数据集，防止处理时间过长
        search_term = f"{query} AND gse[ENTRY]" 
        handle = Entrez.esearch(db="gds", term=search_term, retmax=3)
        record = Entrez.read(handle)
        id_list = record.get("IdList", [])
        
        if not id_list:
            return "❌ 抱歉，在 NCBI GEO 中没有检索到符合条件的数据集。请尝试更换搜索词。"

        # 2. 获取这些数据集的详细信息 (Summary)
        summary_handle = Entrez.esummary(db="gds", id=",".join(id_list))
        summaries = Entrez.read(summary_handle)
        
        # 3. 初始化 OpenAI 的轻量级高性价比向量模型
        embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
        results_for_llm = []
        
        with Session(engine) as session:
            for summary in summaries:
                acc = summary.get("accession", "")  # 如 GSE123456
                title = summary.get("title", "")
                desc = summary.get("summary", "")
                
                # 去重检查：如果数据库里已经有这个 GSE，就跳过向量化以省钱
                existing = session.exec(select(PublicDataset).where(PublicDataset.accession == acc)).first()
                if existing:
                    results_for_llm.append({
                        "accession": acc,
                        "title": title,
                        "summary": desc[:150] + "...",
                        "status": "已存在于本地库"
                    })
                    continue

                # ✨ 核心：将数据集的标题和描述融合成一段文本，并进行 1536 维的向量化！
                text_to_embed = f"Title: {title}\nDescription: {desc}"
                log.info(f"🧠 正在调用 OpenAI API 对 {acc} 进行文本向量化 (Embedding)...")
                vector = embeddings_model.embed_query(text_to_embed)
                
                # 存入 PostgreSQL 的 pgvector 字段
                dataset = PublicDataset(
                    accession=acc,
                    title=title,
                    summary=desc,
                    source_url=f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={acc}",
                    embedding=vector,
                    owner_id=user_id
                )
                session.add(dataset)
                
                results_for_llm.append({
                    "accession": acc,
                    "title": title,
                    "summary": desc[:150] + "...",  # 截断一下发给 LLM，省 Token
                    "status": "已成功检索并向量化"
                })
                
            session.commit()
            
        # 4. 精确指导大模型如何向前端吐出数据卡片
        system_instruction = f"""
        【系统通知】已成功执行工具。查找到的数据如下：
        {json.dumps(results_for_llm, ensure_ascii=False, indent=2)}
        
        【极度重要】请立即向用户汇报结果！并且，请严格使用以下的 Markdown 代码块格式，包裹完整的 JSON 数组，以便前端能够拦截并渲染出【一键分析数据集卡片】：
        
        ```dataset_cards
        [
            {{
                "accession": "GSE...",
                "title": "...",
                "summary": "..."
            }}
        ]
        ```
        请不要在 ```dataset_cards 块里写任何非 JSON 的文本！
        """
        return system_instruction

    except Exception as e:
        log.error(f"GEO 检索失败: {e}")
        return f"❌ 检索外部数据库时发生错误：{str(e)}"


@tool
def submit_async_geo_analysis_task(accession: str, user_id: int, project_id: int) -> str:
    """
    当用户要求使用某个公共数据集(如GSE...)进行分析、或是点击了"一键分析"按钮时，必须调用此工具！
    该工具会将重型生信计算任务投递到后端的 Celery 异步集群，防止阻塞当前对话。
    """
    log.info(f"🤖 Agent 决定投递异步分析任务: {accession} (Project: {project_id})")
    try:
        from app.services.celery_app import run_geo_single_cell_pipeline
        
        # 投递异步任务 (delay)
        task = run_geo_single_cell_pipeline.delay(accession, project_id, user_id)
        
        return f"""
        ✅ 已成功拦截任务并投递至底层超级计算集群！
        任务分配 ID: `{task.id}`。
        
        请温柔地回复用户：
        "您的公共数据集 `{accession}` 已成功移交后台超级计算集群。
        由于单细胞分析（质控、PCA、UMAP降维等）属于重度算力消耗型任务，系统将在后台自动为您执行。
        您可以稍后在右侧的文件中心查看生成的 UMAP 高清图表，或点击左侧【控制面板】->【任务中心】输入 Task ID 查看实时滚动日志！"
        """
    except Exception as e:
        return f"❌ 任务投递失败，集群可能未就绪: {str(e)}"
        log.error(f"GEO 检索失败: {e}")
        return f"❌ 检索外部数据库时发生错误：{str(e)}"
