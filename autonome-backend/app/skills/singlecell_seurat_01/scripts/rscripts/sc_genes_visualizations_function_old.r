library(viridis)
library(scCustomize)

plot_one_gene <- function(gene,clusterid,splitby,assay="RNA"){
    DefaultAssay(sc.combined) <- assay
    Idents(sc.combined) <- sc.idents.bak
    show.num = 1
    cid = clusterid
    colors = c("#0072B2","#eb5d46","#F0E442","#009E73","#CC79A7","#5d8ac4","#f39659","#936355","#999999","#E69F00","#56B4E9","#009E73","#F0E442","#0072B2","#D55E00","#000000","#E69F00","#56B4E9","#D55E00","#CC79A7","#FCFBFD","#EFEDF5","#DADAEB","#BCBDDC","#9E9AC8","#807DBA","#6A51A3","#54278F","#3F007D")


    p1 <- FeaturePlot(sc.combined, reduction = "umap", features = gene, split.by = splitby, min.cutoff = 'q10', 
        cols = c("grey", "red"))
    pdf(file=paste("featureplot_umap_bygroup_",gene,".pdf",sep=""),width = groupnum*4,height = show.num*4)
    print(p1)
    dev.off()

    w = groupnum*100
    h = show.num*100
    if(h>2700){
        h=2700
    }
    png(file = paste("featureplot_umap_bygroup_",gene,".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()

    # #分group展示-tsne
    # p1 <- FeaturePlot(sc.combined, reduction = "tsne", features = gene, split.by = splitby, min.cutoff = 'q10', 
    #     cols = c("grey", "red"))
    # pdf(file=paste("featureplot_tsne_bygroup_",gene,".pdf",sep=""),width = groupnum*4,height = show.num*4)
    # print(p1)
    # dev.off()

    # w = groupnum*100
    # h = show.num*100
    # if(h>2700){
    #     h=2700
    # }
    # png(file = paste("featureplot_tsne_bygroup_",gene,".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    # par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    # print(p1)
    # dev.off()

    #不分group展示-umap
    p1 <- FeaturePlot(sc.combined, reduction = "umap", features = gene, min.cutoff = 'q10', cols = c("grey", "red"),ncol = 1)
    pdf(file=paste("featureplot_umap_",gene,".pdf",sep=""),width = 5,height = show.num*4)
    print(p1)
    dev.off()

    w = 125
    h = show.num*100
    if(h>2700){
        h=2700
    }
    png(file = paste("featureplot_umap_",gene,".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()

    # #不分group展示-tsne
    # p1 <- FeaturePlot(sc.combined, reduction = "tsne", features = gene, min.cutoff = 'q10', cols = c("grey", "red"),ncol = 1)
    # pdf(file=paste("featureplot_tsne_",gene,".pdf",sep=""),width = 5,height = show.num*4)
    # print(p1)
    # dev.off()

    # w = 125
    # h = show.num*100
    # if(h>2700){
    #     h=2700
    # }
    # png(file = paste("featureplot_tsne_",gene,".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    # par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    # print(p1)
    # dev.off()


    ## violin plot 小提琴图

    plots <- VlnPlot(sc.combined, features = gene, split.by = splitby, group.by = "celltype", pt.size = 0, combine = FALSE)
    # plots <- VlnPlot(sc.combined, features = gene, split.by = "celltype", group.by = splitby, pt.size = 0, combine = FALSE, cols = colors)

    pdf(file=paste("DEG_vlnplot_",gene,".pdf",sep=""),width = 1*clusternum,height =  show.num*4)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()

    w = 25*clusternum
    h = show.num*100
    if(h>2700){
        h=2700
    }
    png(file = paste("DEG_vlnplot_",gene,".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()

    ## Ridge plot 山脊图

    # if(cid){
    #     p1 <- RidgePlot(sc.combined, features = gene, group.by=splitby, ncol = 1, idents=cid)
    #     # p1 <- RidgePlot(sc.combined, features = gene, group.by=splitby, ncol = 1)
    #     pdf(file=paste("ridgeplot_",cid,"_",gene,".pdf",sep=""),width = 5,height = show.num*4)
    #     print(p1)
    #     dev.off()

    #     w = 125
    #     h = show.num*100
    #     if(h>2700){
    #         h=2700
    #     }
    #     png(file = paste("ridgeplot_",cid,"_",gene,".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    #     par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    #     print(p1)
    #     dev.off()
    # }

    # p1 <- RidgePlot(sc.combined, features = gene, ncol = 1)
    # pdf(file=paste("ridgeplot_",gene,".pdf",sep=""),width = 5,height = show.num*clusternum*0.3)
    # print(p1)
    # dev.off()

    # w = 125
    # h = show.num*clusternum*7.5
    # if(h>2700){
    #     h=2700
    # }
    # png(file = paste("ridgeplot_",gene,".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    # par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    # print(p1)
    # dev.off()
}

show_genes <- function(genes.to.show,genes.to.show.num,groupnum,clusternum,prefix="",cid=FALSE,splitby="group",assay="RNA"){

    showgene_dir = paste(prefix, sep="")
    if(!file.exists(showgene_dir)){
    dir.create(showgene_dir)
    }
    setwd(showgene_dir)
    DefaultAssay(sc.combined) <- assay
    Idents(sc.combined) <- sc.idents.bak
    ## feature scatter plot 散点图
    #分group展示-umap

    ## 按基因画图
    future_mapply(plot_one_gene,genes.to.show,cid,splitby,future.seed = TRUE)

    ## feature dotplot 点图

    clen<- length(unique(factor(Idents(sc.combined))))-1
    # Idents(sc.combined) <- factor(Idents(sc.combined),levels=rev(c(0:clusternum)))
    Idents(sc.combined) <- factor(Idents(sc.combined),levels=rev(c(0:clen)))

    p1 <- DotPlot(sc.combined, features = unique(genes.to.show), cols = c("#0072B2","#eb5d46","#F0E442","#009E73","#CC79A7","#5d8ac4","#f39659","#936355","#999999","#E69F00","#56B4E9","#009E73","#F0E442","#0072B2","#D55E00","#000000","#E69F00","#56B4E9","#D55E00","#CC79A7","#FCFBFD","#EFEDF5","#DADAEB","#BCBDDC","#9E9AC8","#807DBA","#6A51A3","#54278F","#3F007D"), dot.scale =10, split.by = "group") + 
        RotatedAxis()
    pdf(file=paste("Dotplot",".pdf",sep=""),width = 0.8*genes.to.show.num+2,height = 0.8*clusternum)
    print(p1)
    dev.off()

    w = 20*genes.to.show.num+50
    h = 20*clusternum
    if(h>2700){
        h=2700
    }
    png(file = paste("Dotplot",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()


    
    ## feature heatmap 热图
    tryCatch(
      {
        ## plot top markers heatmap
    
        DefaultAssay(sc.combined) <- assay
        Idents(sc.combined) <- sc.idents.bak
        Idents(sc.combined) <- factor(Idents(sc.combined),levels=rev(c(0:clen)))
        # DefaultAssay(sc.combined) <- assay

        p1 <- DoHeatmap(sc.combined, features = genes.to.show, cells = 1:500, size = 4, angle = 45)
        pdf(file=paste("DoHeatmap",".pdf",sep=""),width = 0.4*clusternum,height = 0.6*genes.to.show.num)
        print(p1+NoLegend())
        dev.off()

        w = 10*clusternum
        h = 15*genes.to.show.num
        if(h>2700){
            h=2700
        }
        png(file = paste("DoHeatmap",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
        par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
        print(p1+NoLegend())
        dev.off()

        if(cid){
            subcells = subset(sc.combined, idents = cid)
            p1 <- DoHeatmap(subcells, features = genes.to.show, group.by = "group",cells = 1:500, size = 4, angle = 45)
            pdf(file=paste("DoHeatmap_bygroup",".pdf",sep=""),width = groupnum*2,height = 0.4*genes.to.show.num)
            print(p1+NoLegend())
            dev.off()

            w = groupnum*50
            h = 10*genes.to.show.num
            if(h>2700){
                h=2700
            }
            png(file = paste("DoHeatmap_bygroup",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
            par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
            print(p1+NoLegend())
            dev.off()
        }


      },
      error=function(cond) {
        ret_code <<- -1
      },

      finally={
        print("画doheatmap的基因不在可变基因中")
        DefaultAssay(sc.combined) <- assay
      })

      setwd("../")

    
}



#####################################################################################
## 两个基因的cell scatter plot方式展示
#####################################################################################

show_pair_gene <- function(gene1,gene2){
    p1 <- FeatureScatter(sc.combined, feature1 = gene1, feature2 = gene2,prefix="")
    pdf(file=paste(prefix,"_Ccn1_vs_Gfra2_feature_scatter",".pdf",sep=""),width = 5,height = 4)
    print(p1)
    dev.off()

    png(file = paste(prefix,"_Ccn1_vs_Gfra2_feature_scatter",".png",sep=""),width = 125,height = 100,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()
}


#####################################################################################
## vlnplot 展示
#####################################################################################



plot_one_gene_vlnplot <- function(gene,clusterid,splitby,assay="RNA"){
    DefaultAssay(sc.combined) <- assay
    Idents(sc.combined) <- sc.idents.bak
    show.num = 1
    cid = clusterid
    colors = c("#0072B2","#eb5d46","#F0E442","#009E73","#CC79A7","#5d8ac4","#f39659","#936355","#999999","#E69F00","#56B4E9","#009E73","#F0E442","#0072B2","#D55E00","#000000","#E69F00","#56B4E9","#D55E00","#CC79A7","#FCFBFD","#EFEDF5","#DADAEB","#BCBDDC","#9E9AC8","#807DBA","#6A51A3","#54278F","#3F007D")

    ## violin plot 小提琴图

    plots <- VlnPlot(sc.combined, features = gene, split.by = splitby, group.by = "celltype", pt.size = 0, combine = FALSE)
    # plots <- VlnPlot(sc.combined, features = gene, split.by = "celltype", group.by = splitby, pt.size = 0, combine = FALSE, cols = colors)

    pdf(file=paste("DEG_vlnplot_",gene,".pdf",sep=""),width = 1*clusternum,height =  show.num*4)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()

    w = 25*clusternum
    h = show.num*100
    if(h>2700){
        h=2700
    }
    png(file = paste("DEG_vlnplot_",gene,".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()


    plots <- VlnPlot(sc.combined, features = gene, group.by = splitby, pt.size = 0, combine = FALSE)
    # plots <- VlnPlot(sc.combined, features = gene, split.by = "celltype", group.by = splitby, pt.size = 0, combine = FALSE, cols = colors)

    pdf(file=paste("DEG_vlnplot2_",gene,".pdf",sep=""),width = 1*clusternum,height =  show.num*4)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()

    w = 25*clusternum
    h = show.num*100
    if(h>2700){
        h=2700
    }
    png(file = paste("DEG_vlnplot2_",gene,".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()


    plots <- VlnPlot(sc.combined, features = gene, split.by = splitby, group.by = "customclassif", pt.size = 0, combine = FALSE)
    # plots <- VlnPlot(sc.combined, features = gene, split.by = "celltype", group.by = splitby, pt.size = 0, combine = FALSE, cols = colors)

    pdf(file=paste("DEG_vlnplot3_",gene,".pdf",sep=""),width = 1*clusternum,height =  show.num*4)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()
    
    w = 25*clusternum
    h = show.num*100
    if(h>2700){
        h=2700
    }
    png(file = paste("DEG_vlnplot3_",gene,".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()


}

show_genes_vlnplot <- function(genes.to.show,genes.to.show.num,groupnum,clusternum,prefix="",cid=FALSE,splitby="group",assay="RNA"){

    showgene_dir = paste(prefix, sep="")
    if(!file.exists(showgene_dir)){
    dir.create(showgene_dir)
    }
    setwd(showgene_dir)
    DefaultAssay(sc.combined) <- assay
    Idents(sc.combined) <- sc.idents.bak
    ## feature scatter plot 散点图
    #分group展示-umap

    ## 按基因画图
    future_mapply(plot_one_gene_vlnplot,genes.to.show,cid,splitby,future.seed = TRUE)

}
