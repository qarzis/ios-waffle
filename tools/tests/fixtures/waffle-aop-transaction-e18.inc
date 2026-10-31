static inline enum waffle_aop_qmp_result
legacy_transaction_run(const struct waffle_aop_qmp_io *io, bool acd,
    void (*task)(void *), void *task_context)
{
    if (!io || !io->read || !io->write || !io->kick || !io->wait)
        return WAFFLE_AOP_QMP_REFUSED;
    void *c = io->context;
    struct waffle_aop_qmp_snapshot s = {
        .magic = io->read(c, 0), .version = io->read(c, 4),
        .our_box_size = io->read(c, 0x34), .our_box = io->read(c, 0x38),
    };
    if (!waffle_aop_qmp_geometry_valid(&s)) return WAFFLE_AOP_QMP_REFUSED;
    /* Refuse busy, partially open or unknown states before the first write. */
    if (io->read(c, 0x0c) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x10) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x14) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x18) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x24) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x28) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x2c) != WAFFLE_AOP_QMP_DOWN ||
        io->read(c, 0x30) != WAFFLE_AOP_QMP_DOWN ||
        io->read(c, s.our_box) != 0) return WAFFLE_AOP_QMP_REFUSED;

    io->write(c, 0x2c, WAFFLE_AOP_QMP_UP);
    io->kick(c);
    bool opened = io->wait(c, 0x14, WAFFLE_AOP_QMP_UP);
    if (opened) {
        /* Remote channel was already acknowledged; publish that ACK again
         * before waiting for AOP to acknowledge our channel, as native does. */
        io->write(c, 0x18, WAFFLE_AOP_QMP_UP);
        io->kick(c);
        opened = io->wait(c, 0x30, WAFFLE_AOP_QMP_UP);
    }
    enum waffle_aop_qmp_result payload = WAFFLE_AOP_QMP_OK;
    bool off_failed = false;
    if (opened && acd) {
        payload = waffle_aop_qmp_send_acd(io, true);
        if (payload == WAFFLE_AOP_QMP_OK && task) task(task_context);
        /* Even an unacknowledged on may have been consumed. Always send off. */
        off_failed = waffle_aop_qmp_send_acd(io, false) != WAFFLE_AOP_QMP_OK;
    }
    io->write(c, 0x2c, WAFFLE_AOP_QMP_DOWN);
    io->kick(c);
    if (!io->wait(c, 0x30, WAFFLE_AOP_QMP_DOWN) ||
        io->read(c, 0x2c) != WAFFLE_AOP_QMP_DOWN ||
        io->read(c, 0x24) != WAFFLE_AOP_QMP_UP ||
        io->read(c, 0x28) != WAFFLE_AOP_QMP_UP)
        return WAFFLE_AOP_QMP_RESTORE_FAILED;
    if (off_failed) return WAFFLE_AOP_QMP_RESTORE_FAILED;
    return opened ? payload : WAFFLE_AOP_QMP_TIMEOUT;
}

