// FastQC + MultiQC Pipeline Module
// 自动生成质量控制报告

process FASTQC {
    tag "${sample_id}"
    cpus params.threads_per_sample ?: 4
    memory '4.GB'

    input:
    tuple val(sample_id), path(reads)

    output:
    path "fastqc_${sample_id}_*", emit: qc_reports

    script:
    """
    fastqc -t ${task.cpus} -o . ${reads}
    """
}

process MULTIQC {
    cpus 2
    memory '2.GB'

    input:
    path fastqc_reports

    output:
    path "multiqc_report.html", emit: report
    path "multiqc_data", emit: data

    script:
    """
    multiqc . -o .
    """
}

workflow FASTQC_MULTIQC_PIPELINE_01 {
    // 参数
    def fastq_dir = params.fastq_dir ?: './fastq'
    def is_paired = params.is_paired_end ?: true
    def pattern = params.file_pattern ?: '*_{1,2}.fastq.gz'

    // 创建输入通道
    Channel
        .fromFilePairs("${fastq_dir}/${pattern}", flat: true)
        .set { samples }

    // 执行 FastQC
    FASTQC(samples)

    // 汇总报告
    MULTIQC(FASTQC.out.qc_reports.collect())
}