library(viridis)
library(scCustomize)
library(RColorBrewer)

plot_one_gene <- function(gene,clusterid,splitby,assay="RNA"){
    DefaultAssay(sc.combined) <- assay
    Idents(sc.combined) <- sc.idents.bak
    show.num = 1
    cid = clusterid
    colors = c("#0072B2","#eb5d46","#F0E442","#009E73","#CC79A7","#5d8ac4","#f39659","#936355","#999999","#E69F00","#56B4E9","#009E73","#F0E442","#0072B2","#D55E00","#000000","#E69F00","#56B4E9","#D55E00","#CC79A7","#FCFBFD","#EFEDF5","#DADAEB","#BCBDDC","#9E9AC8","#807DBA","#6A51A3","#54278F","#3F007D")


    p1 <- FeaturePlot_scCustom(sc.combined, reduction = "umap", features = gene, split.by = splitby, order = F,alpha_exp=0.75,alpha_na_exp=0.75, raster = F)
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
    # p1 <- FeaturePlot_scCustom(sc.combined, reduction = "tsne", features = gene, split.by = splitby,,alpha_exp=0.75,alpha_na_exp=0.75, raster = F 
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
    p1 <- FeaturePlot_scCustom(sc.combined, reduction = "umap", features = gene,num_columns = 1, order = F,alpha_exp=0.75,alpha_na_exp=0.75, raster = F)
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
    # p1 <- FeaturePlot_scCustom(sc.combined, reduction = "tsne", features = gene,ncol = 1,alpha_exp=0.75,alpha_na_exp=0.75, raster = F)
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
    
    # by cluster
    plots <- VlnPlot_scCustom(sc.combined, features = gene, split.by = splitby, group.by = "seurat_clusters",pt.size=0)
    # plots <- VlnPlot_scCustom(sc.combined, features = gene, split.by = "celltype", group.by = splitby, cols = colors)

    pdf(file=paste("DEG_vlnplot_",gene,".bycluster.pdf",sep=""),width = 1*clusternum,height =  show.num*4)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()

    w = 25*clusternum
    h = show.num*100
    if(h>2700){
        h=2700
    }
    png(file = paste("DEG_vlnplot_",gene,".bycluster.png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()

    # by celltype
    cellclassnum = length(unique(factor(sc.combined$customclassif)))
    plots <- VlnPlot_scCustom(sc.combined, features = gene, split.by = splitby, group.by = "customclassif",pt.size=0)
    # plots <- VlnPlot_scCustom(sc.combined, features = gene, split.by = "celltype", group.by = splitby, cols = colors)

    pdf(file=paste("DEG_vlnplot_",gene,".bycelltype.pdf",sep=""),width = 1.2*cellclassnum+1,height =  show.num*4)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()

    w = 30*cellclassnum+25
    h = show.num*100
    if(h>2700){
        h=2700
    }
    png(file = paste("DEG_vlnplot_",gene,".bycelltype.png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()

    # by group
    
    plots <- VlnPlot_scCustom(sc.combined, features = gene, group.by = splitby,pt.size=0)
    # plots <- VlnPlot_scCustom(sc.combined, features = gene, split.by = "celltype", group.by = splitby, cols = colors)

    pdf(file=paste("DEG_vlnplot_",gene,".bygroup.pdf",sep=""),width = 1.5*groupnum+1,height =  show.num*4)
    print(wrap_plots(plots = plots, ncol = 1))
    dev.off()

    w = 37.5*groupnum+25
    h = show.num*100
    if(h>2700){
        h=2700
    }
    png(file = paste("DEG_vlnplot_",gene,".bygroup.png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
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

plot_one_gene_dotplot <- function(gene,grouplevel=grouplevel){
    #####第二个方法，增加一个customclassif_group 的metadata 然后再将一列拆分成六列
##添加一个customclassif_group的列
customclassif_group <- paste0(sc.combined@meta.data[["customclassif"]], "-", sc.combined@meta.data[["group"]])
sc.combined@meta.data[["customclassif_group"]] <- customclassif_group
 
##获取dotplot的数据
dotplot_data_all_gene_customclassif_group <- DotPlot(sc.combined, features = gene, group.by = 'customclassif_group')$data
print(dotplot_data_all_gene_customclassif_group)
cat('',file=paste(gene,'_dotplot.data.bycelltype_group','.xls',sep=''))
write.table(dotplot_data_all_gene_customclassif_group,file=paste(gene,'_dotplot.data.bycelltype_group','.xls',sep=''),
                append=T,quote=F,sep='\t',row.names = TRUE,col.names = TRUE)
##删除percentage = 0的数据
# delete <- c()
# for (i in c(1:255)) {

#   if (dotplot_data_all_gene_customclassif_group[i,2] == 0) {
#     delete <- c(delete, i)
#   }
# }
 
# install.packages("stringr")
library(stringr)
 
# dotplot_data_all_gene_customclassif_group$features.plot <- str_extract(dotplot_data_all_gene_customclassif_group$id,'^([A-Za-z0-9_]+)')
 
a <- str_extract(dotplot_data_all_gene_customclassif_group$id,'^([A-Za-z0-9_\']+)')
b <- str_extract(dotplot_data_all_gene_customclassif_group$id,'^([A-Za-z0-9_\']+) ([A-Za-z0-9_\']+)')
c <- str_extract(dotplot_data_all_gene_customclassif_group$id,'^([A-Za-z0-9_\']+) ([A-Za-z0-9_\']+) ([A-Za-z0-9_\']+)')
 
for (i in c(1:length(a))) {
  if (!is.na(c[i])) {
    a[i] <- c[i]
  }
  else if (!is.na(b[i])) {
    a[i] <- b[i]
  }
}
 
dotplot_data_all_gene_customclassif_group$features.plot <- a
 




 
# dotplot_data_all_gene_customclassif_group <- dotplot_data_all_gene_customclassif_group[-delete,]
 
a <- str_extract(dotplot_data_all_gene_customclassif_group$id,'([A-Za-z0-9_]+)$')
b <- str_extract(dotplot_data_all_gene_customclassif_group$id,'([A-Za-z0-9_]+) ([A-Za-z0-9_]+)$')
c <- str_extract(dotplot_data_all_gene_customclassif_group$id,'([A-Za-z0-9_]+) ([A-Za-z0-9_]+) ([A-Za-z0-9_]+)$')
 
for (i in c(1:length(a))) {
  if (!is.na(c[i])) {
    a[i] <- c[i]
  }
  else if (!is.na(b[i])) {
    a[i] <- b[i]
  }
}
 
dotplot_data_all_gene_customclassif_group$id <- a



# dotplot_data_all_gene_customclassif_group$id <- factor(dotplot_data_all_gene_customclassif_group$id, levels= grouplevel)
 
##绘图
p=ggplot(dotplot_data_all_gene_customclassif_group,aes(x=features.plot,y = id,size = pct.exp, color = avg.exp.scaled))+
  geom_point() + 
  scale_size("Percent\nExpressed", range = c(0,10)) +
  scale_y_discrete(position = "left") +
  scale_color_gradientn(colours = brewer.pal(5, "Reds"),
                        guide = guide_colorbar(ticks.colour = "black",frame.colour = "black"),
                        name = "Average\nexpression") +
  cowplot::theme_cowplot() +
  ylab("Identity") + xlab("Features") + 
  theme_bw(base_rect_size = 2, base_line_size = 1) +
  theme(
    axis.text.x = element_text(size=10, angle=45, vjust = 1,hjust = 1, color="black", lineheight = 10),
    axis.text.y = element_text(size=12, color="black"),
    axis.title = element_text(size=14),
  )

ggsave(paste("DEG_dotplot_",gene,".bycelltype.png",sep = ""),p,width = 8,height = 5,dpi = 300)
ggsave(paste("DEG_dotplot_",gene,".bycelltype.pdf",sep = ""),p,width = 8,height = 5)

}

plot_one_gene_dotplot2 <- function(gene){
    #####第二个方法，增加一个seurat_clusters_group 的metadata 然后再将一列拆分成六列
##添加一个seurat_clusters_group的列
seurat_clusters_group <- paste0(sc.combined@meta.data[["seurat_clusters"]], "-", sc.combined@meta.data[["group"]])
sc.combined@meta.data[["seurat_clusters_group"]] <- seurat_clusters_group
 
##获取dotplot的数据
dotplot_data_all_gene_seurat_clusters_group <- DotPlot(sc.combined, features = gene, group.by = 'seurat_clusters_group')$data
print(dotplot_data_all_gene_seurat_clusters_group)
cat('',file=paste(gene,'_dotplot.data.bycluster_group','.xls',sep=''))
write.table(dotplot_data_all_gene_seurat_clusters_group,file=paste(gene,'_dotplot.data.bycluster_group','.xls',sep=''),
                append=T,quote=F,sep='\t',row.names = FALSE,col.names = TRUE)
##删除percentage = 0的数据
# delete <- c()
# for (i in c(1:255)) {

#   if (dotplot_data_all_gene_seurat_clusters_group[i,2] == 0) {
#     delete <- c(delete, i)
#   }
# }
 
# install.packages("stringr")
library(stringr)
 
# dotplot_data_all_gene_seurat_clusters_group$features.plot <- str_extract(dotplot_data_all_gene_seurat_clusters_group$id,'^([A-Za-z0-9_]+)')
 


a <- str_extract(dotplot_data_all_gene_seurat_clusters_group$id,'^([A-Za-z0-9_\']+)')
b <- str_extract(dotplot_data_all_gene_seurat_clusters_group$id,'^([A-Za-z0-9_\']+) ([A-Za-z0-9_\']+)')
c <- str_extract(dotplot_data_all_gene_seurat_clusters_group$id,'^([A-Za-z0-9_\']+) ([A-Za-z0-9_\']+) ([A-Za-z0-9_\']+)')
 
for (i in c(1:length(a))) {
  if (!is.na(c[i])) {
    a[i] <- c[i]
  }
  else if (!is.na(b[i])) {
    a[i] <- b[i]
  }
}
 
dotplot_data_all_gene_seurat_clusters_group$features.plot <- a
 


 
# dotplot_data_all_gene_seurat_clusters_group <- dotplot_data_all_gene_seurat_clusters_group[-delete,]
 
a <- str_extract(dotplot_data_all_gene_seurat_clusters_group$id,'([A-Za-z0-9_]+)$')
b <- str_extract(dotplot_data_all_gene_seurat_clusters_group$id,'([A-Za-z0-9_]+) ([A-Za-z0-9_]+)$')
c <- str_extract(dotplot_data_all_gene_seurat_clusters_group$id,'([A-Za-z0-9_]+) ([A-Za-z0-9_]+) ([A-Za-z0-9_]+)$')
 
for (i in c(1:length(a))) {
  if (!is.na(c[i])) {
    a[i] <- c[i]
  }
  else if (!is.na(b[i])) {
    a[i] <- b[i]
  }
}
 
dotplot_data_all_gene_seurat_clusters_group$id <- a
 
##绘图
p=ggplot(dotplot_data_all_gene_seurat_clusters_group,aes(x=features.plot,y = id,size = pct.exp, color = avg.exp.scaled))+
  geom_point() + 
  scale_size("Percent\nExpressed", range = c(0,10)) +
  scale_y_discrete(position = "left") +
  scale_color_gradientn(colours = brewer.pal(5, "Reds"),
                        guide = guide_colorbar(ticks.colour = "black",frame.colour = "black"),
                        name = "Average\nexpression") +
  cowplot::theme_cowplot() +
  ylab("Identity") + xlab("Features") + 
  theme_bw(base_rect_size = 2, base_line_size = 1) +
  theme(
    axis.text.x = element_text(size=10, angle=0, hjust=0.5, color="black", lineheight = 10),
    axis.text.y = element_text(size=12, color="black"),
    axis.title = element_text(size=14),
  )

ggsave(paste("DEG_dotplot_",gene,".bycluster.png",sep = ""),p,width = 8,height = 5,dpi = 300)
ggsave(paste("DEG_dotplot_",gene,".bycluster.pdf",sep = ""),p,width = 8,height = 5)

}


show_genes <- function(genes.to.show,genes.to.show.num,groupnum,clusternum,prefix="",cid=FALSE,splitby="group",assay="RNA",onlydotplot=FALSE,grouplevel=""){

    showgene_dir = paste(prefix, sep="")
    if(!file.exists(showgene_dir)){
    dir.create(showgene_dir)
    }
    setwd(showgene_dir)
    DefaultAssay(sc.combined) <- assay
    Idents(sc.combined) <- sc.idents.bak

    # 首先，提取原始行名
    # original_row_names <- rownames(sc.combined[["group"]])

    # # 然后，使用 unlist 转换数据，并将原始行名应用于结果向量
    # unlisted_vector <- unlist(sc.combined[["group"]])
    # names(unlisted_vector) <- original_row_names

    # # 查看结果
    # head(unlisted_vector)



    # sc.combined[["group"]] <- factor(unlisted_vector, levels= grouplevel)




    ## feature scatter plot 散点图
    #分group展示-umap

    ## 按基因画图
    if(!onlydotplot){
        future_mapply(plot_one_gene_dotplot,genes.to.show,grouplevel,future.seed = TRUE)
        future_mapply(plot_one_gene_dotplot2,genes.to.show,future.seed = TRUE)
        future_mapply(plot_one_gene,genes.to.show,cid,splitby,assay,future.seed = TRUE)
    }

    ## feature dotplot 点图


    # # dotplot by group
    # Idents(sc.combined) <- "group"

    # # if(!grouplevel){
    # #     Idents(sc.combined) <- factor(sc.combined@active.ident, sort(levels(sc.combined@active.ident)))
    # # }
    # # else{
    # #     Idents(sc.combined) <- factor(Idents(sc.combined), levels= grouplevel)
    # # }
    # Idents(sc.combined) <- factor(Idents(sc.combined), levels= grouplevel)

    # p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = F, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    # pdf(file=paste("Dotplot_bygroup",".pdf",sep=""),width = 0.4*genes.to.show.num+4,height = 0.6*groupnum+4)
    # print(p1)
    # dev.off()

    # w = 10*genes.to.show.num+100
    # h = 15*groupnum+100
    # if(h>2700){
    #     h=2700
    # }
    # png(file = paste("Dotplot_bygroup",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    # par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    # print(p1)
    # dev.off()


    # p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = T, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    # pdf(file=paste("Dotplot_bygroup_flip",".pdf",sep=""),height = 0.4*genes.to.show.num+4,width = 0.6*groupnum+4)
    # print(p1)
    # dev.off()

    # w = 10*genes.to.show.num+100
    # h = 15*groupnum+100
    # if(h>2700){
    #     h=2700
    # }
    # png(file = paste("Dotplot_bygroup_flip",".png",sep=""),height = w,width = h,units = "mm",res = 300,pointsize = 2)
    # par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    # print(p1)
    # dev.off()








    # dotplot by celltype
    sc.combined$cellclass.group <- paste(sc.combined$customclassif, sc.combined$group, sep = "_")
    sc.combined$cellclass <- sc.combined$customclassif
    # Idents(sc.combined) <- "cellclass.group"
    Idents(sc.combined) <- "customclassif"
    cellclassnum = length(unique(sc.combined$customclassif))


    p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = F, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    pdf(file=paste("Dotplot_bycelltype",".pdf",sep=""),width = 0.4*genes.to.show.num+4,height = 0.4*cellclassnum+4)
    print(p1)
    dev.off()

    w = 10*genes.to.show.num+100
    h = 10*cellclassnum+100
    if(h>2700){
        h=2700
    }
    png(file = paste("Dotplot_bycelltype",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()

    p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = T, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    pdf(file=paste("Dotplot_bycelltype_flip",".pdf",sep=""),height = 0.4*genes.to.show.num+4,width = 0.6*cellclassnum+4)
    print(p1)
    dev.off()

    w = 10*genes.to.show.num+100
    h = 15*cellclassnum+100
    if(h>2700){
        h=2700
    }
    png(file = paste("Dotplot_bycelltype_flip",".png",sep=""),height = w,width = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()




    # dotplot by celltype_group
    sc.combined$cellclass.group <- paste(sc.combined$customclassif, sc.combined$group, sep = "_")
    sc.combined$cellclass <- sc.combined$customclassif
    Idents(sc.combined) <- "cellclass.group"
    # Idents(sc.combined) <- "customclassif"
    cellclassnum = length(unique(sc.combined$cellclass.group))
    mylevels = sort(unique(sc.combined$cellclass.group),decreasing=TRUE)

    Idents(sc.combined) <- factor(Idents(sc.combined), levels= mylevels)


    p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = F, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    pdf(file=paste("Dotplot_bycelltype_group",".pdf",sep=""),width = 0.4*genes.to.show.num+4,height = 0.4*cellclassnum+4)
    print(p1)
    dev.off()

    w = 10*genes.to.show.num+100
    h = 10*cellclassnum+100
    if(h>2700){
        h=2700
    }
    png(file = paste("Dotplot_bycelltype_group",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()

    p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = T, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    pdf(file=paste("Dotplot_bycelltype_group_flip",".pdf",sep=""),height = 0.4*genes.to.show.num+4,width = 0.6*cellclassnum+4)
    print(p1)
    dev.off()

    w = 10*genes.to.show.num+100
    h = 15*cellclassnum+100
    if(h>2700){
        h=2700
    }
    png(file = paste("Dotplot_bycelltype_group_flip",".png",sep=""),height = w,width = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()



# # 物种+细胞类型
#     # dotplot by celltype_species
#     sc.combined$cellclass.species <- paste(sc.combined$customclassif, sc.combined$species, sep = "_")
#     sc.combined$cellclass <- sc.combined$customclassif
#     Idents(sc.combined) <- "cellclass.species"
#     # Idents(sc.combined) <- "customclassif"
#     cellclassnum = length(unique(sc.combined$cellclass.species))
#     mylevels = sort(unique(sc.combined$cellclass.species),decreasing=TRUE)

#     Idents(sc.combined) <- factor(Idents(sc.combined), levels= mylevels)


#     p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = F, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
#     pdf(file=paste("Dotplot_bycelltype_species",".pdf",sep=""),width = 0.4*genes.to.show.num+4,height = 0.4*cellclassnum+4)
#     print(p1)
#     dev.off()

#     w = 10*genes.to.show.num+100
#     h = 10*cellclassnum+100
#     if(h>2700){
#         h=2700
#     }
#     png(file = paste("Dotplot_bycelltype_species",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
#     par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
#     print(p1)
#     dev.off()

#     p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = T, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
#     pdf(file=paste("Dotplot_bycelltype_species_flip",".pdf",sep=""),height = 0.4*genes.to.show.num+4,width = 0.6*cellclassnum+4)
#     print(p1)
#     dev.off()

#     w = 10*genes.to.show.num+100
#     h = 15*cellclassnum+100
#     if(h>2700){
#         h=2700
#     }
#     png(file = paste("Dotplot_bycelltype_species_flip",".png",sep=""),height = w,width = h,units = "mm",res = 300,pointsize = 2)
#     par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
#     print(p1)
#     dev.off()





    # dotplot by group
    Idents(sc.combined) <- "group"

    # if(!grouplevel){
    #     Idents(sc.combined) <- factor(sc.combined@active.ident, sort(levels(sc.combined@active.ident)))
    # }
    # else{
    #     Idents(sc.combined) <- factor(Idents(sc.combined), levels= grouplevel)
    # }
    Idents(sc.combined) <- factor(Idents(sc.combined), levels= grouplevel)

    p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = F, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    pdf(file=paste("Dotplot_bygroup",".pdf",sep=""),width = 0.4*genes.to.show.num+4,height = 0.6*groupnum+4)
    print(p1)
    dev.off()

    w = 10*genes.to.show.num+100
    h = 15*groupnum+100
    if(h>2700){
        h=2700
    }
    png(file = paste("Dotplot_bygroup",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()


    p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = T, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    pdf(file=paste("Dotplot_bygroup_flip",".pdf",sep=""),height = 0.4*genes.to.show.num+4,width = 0.6*groupnum+4)
    print(p1)
    dev.off()

    w = 10*genes.to.show.num+100
    h = 15*groupnum+100
    if(h>2700){
        h=2700
    }
    png(file = paste("Dotplot_bygroup_flip",".png",sep=""),height = w,width = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()


## by replicate


    # dotplot by group
    Idents(sc.combined) <- "replicate"
    samplenum = length(unique(factor(sc.combined$replicate)))

    # if(!grouplevel){
    #     Idents(sc.combined) <- factor(sc.combined@active.ident, sort(levels(sc.combined@active.ident)))
    # }
    # else{
    #     Idents(sc.combined) <- factor(Idents(sc.combined), levels= grouplevel)
    # }
    # Idents(sc.combined) <- factor(Idents(sc.combined), levels= grouplevel)

    p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = F, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    pdf(file=paste("Dotplot_byreplicate",".pdf",sep=""),width = 0.4*genes.to.show.num+4,height = 0.4*samplenum+4)
    print(p1)
    dev.off()

    w = 10*genes.to.show.num+100
    h = 10*samplenum+100
    if(h>2700){
        h=2700
    }
    png(file = paste("Dotplot_byreplicate",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()


    p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = T, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    pdf(file=paste("Dotplot_byreplicate_flip",".pdf",sep=""),height = 0.4*genes.to.show.num+4,width = 0.4*samplenum+4)
    print(p1)
    dev.off()

    w = 10*genes.to.show.num+100
    h = 10*samplenum+100
    if(h>2700){
        h=2700
    }
    png(file = paste("Dotplot_byreplicate_flip",".png",sep=""),height = w,width = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()


    # dotplot by cluster
    # clen<- length(unique(factor(Idents(sc.combined))))-1
    # # Idents(sc.combined) <- factor(Idents(sc.combined),levels=rev(c(0:clusternum)))
    # Idents(sc.combined) <- factor(Idents(sc.combined),levels=rev(c(0:clen)))
    Idents(sc.combined) <- "seurat_clusters"

    p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = F, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    pdf(file=paste("Dotplot_bycluster",".pdf",sep=""),width = 0.4*genes.to.show.num+4,height = 0.4*clusternum+4)
    print(p1)
    dev.off()

    w = 10*genes.to.show.num+100
    h = 10*clusternum+100
    if(h>2700){
        h=2700
    }
    png(file = paste("Dotplot_bycluster",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()


    # dotplot by cluster_group
    sc.combined$cellclass.group <- paste(sc.combined$seurat_clusters, sc.combined$group, sep = "_")
    sc.combined$cellclass <- sc.combined$seurat_clusters
    Idents(sc.combined) <- "cellclass.group"
    # Idents(sc.combined) <- "seurat_clusters"
    cellclassnum = length(unique(sc.combined$cellclass.group))
    mylevels = sort(unique(sc.combined$cellclass.group),decreasing=TRUE)

    Idents(sc.combined) <- factor(Idents(sc.combined), levels= mylevels)


    p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = F, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    pdf(file=paste("Dotplot_bycluster_group",".pdf",sep=""),width = 0.4*genes.to.show.num+4,height = 0.4*cellclassnum+4)
    print(p1)
    dev.off()

    w = 10*genes.to.show.num+100
    h = 10*cellclassnum+100
    if(h>2700){
        h=2700
    }
    png(file = paste("Dotplot_bycluster_group",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()

    p1 <- DotPlot_scCustom(seurat_object = sc.combined, features = unique(genes.to.show), flip_axes = T, x_lab_rotate = TRUE,colors_use = viridis_plasma_dark_high)
    pdf(file=paste("Dotplot_bycluster_group_flip",".pdf",sep=""),height = 0.4*genes.to.show.num+4,width = 0.6*cellclassnum+4)
    print(p1)
    dev.off()

    w = 10*genes.to.show.num+100
    h = 15*cellclassnum+100
    if(h>2700){
        h=2700
    }
    png(file = paste("Dotplot_bycluster_group_flip",".png",sep=""),height = w,width = h,units = "mm",res = 300,pointsize = 2)
    par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    print(p1)
    dev.off()



    
    # ## feature heatmap 热图
    # tryCatch(
    #   {
    #     ## plot top markers heatmap
    
    #     DefaultAssay(sc.combined) <- assay
    #     Idents(sc.combined) <- sc.idents.bak
    #     Idents(sc.combined) <- factor(Idents(sc.combined),levels=rev(c(0:clen)))
    #     # DefaultAssay(sc.combined) <- assay

    #     p1 <- DoHeatmap(sc.combined, features = genes.to.show, cells = 1:500, size = 4, angle = 45)
    #     pdf(file=paste("DoHeatmap",".pdf",sep=""),width = 0.4*clusternum,height = 0.6*genes.to.show.num)
    #     print(p1+NoLegend())
    #     dev.off()

    #     w = 10*clusternum
    #     h = 15*genes.to.show.num
    #     if(h>2700){
    #         h=2700
    #     }
    #     png(file = paste("DoHeatmap",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    #     par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    #     print(p1+NoLegend())
    #     dev.off()

    #     if(cid){
    #         subcells = subset(sc.combined, idents = cid)
    #         p1 <- DoHeatmap(subcells, features = genes.to.show, group.by = "group",cells = 1:500, size = 4, angle = 45)
    #         pdf(file=paste("DoHeatmap_bygroup",".pdf",sep=""),width = groupnum*2,height = 0.4*genes.to.show.num)
    #         print(p1+NoLegend())
    #         dev.off()

    #         w = groupnum*50
    #         h = 10*genes.to.show.num
    #         if(h>2700){
    #             h=2700
    #         }
    #         png(file = paste("DoHeatmap_bygroup",".png",sep=""),width = w,height = h,units = "mm",res = 300,pointsize = 2)
    #         par(mar = c(5, 5, 2, 2), cex.axis = 2, cex.lab = 2)
    #         print(p1+NoLegend())
    #         dev.off()
    #     }


    #   },
    #   error=function(cond) {
    #     print("画doheatmap的基因不在可变基因中")
    #     ret_code <<- -1
    #   },

    #   finally={
    #     DefaultAssay(sc.combined) <- assay
    #   })

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
