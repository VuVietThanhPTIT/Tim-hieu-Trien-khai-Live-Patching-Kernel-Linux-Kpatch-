#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/irqflags.h>

MODULE_LICENSE("GPL");

static unsigned long gpa = 0;
module_param(gpa, ulong, 0644);

static int __init touch_cli_init(void) {
    void *vaddr;
    if (!gpa) {
        pr_err("touch_cli: no GPA specified\n");
        return -EINVAL;
    }
    pr_info("touch_cli: Mapping GPA 0x%lx\n", gpa);

    vaddr = memremap(gpa, 4096, MEMREMAP_WB);
    if (!vaddr) {
        pr_err("touch_cli: memremap failed\n");
        return -ENOMEM;
    }

    pr_info("touch_cli: Executing synchronous touch...\n");
    local_irq_disable();
    *(volatile char *)vaddr = 0xAA;
    local_irq_enable();

    pr_info("touch_cli: Touch completed successfully!\n");
    memunmap(vaddr);
    return 0;
}

static void __exit touch_cli_exit(void) {
    pr_info("touch_cli: exit\n");
}

module_init(touch_cli_init);
module_exit(touch_cli_exit);
