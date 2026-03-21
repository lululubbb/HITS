package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;
import java.util.HashMap;
import java.util.Map;

class CSVRecord_9_6Test {

    @Test
    @Timeout(8000)
    void testGetComment_NonNullComment() throws Exception {
        String[] values = new String[] {"a", "b"};
        Map<String, Integer> mapping = new HashMap<>();
        String comment = "This is a comment";
        long recordNumber = 1L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        if (Modifier.isPrivate(constructor.getModifiers()) || !constructor.canAccess(null)) {
            constructor.setAccessible(true);
        }
        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        assertEquals(comment, record.getComment());
    }

    @Test
    @Timeout(8000)
    void testGetComment_NullComment() throws Exception {
        String[] values = new String[] {"a", "b"};
        Map<String, Integer> mapping = new HashMap<>();
        String comment = null;
        long recordNumber = 1L;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        if (Modifier.isPrivate(constructor.getModifiers()) || !constructor.canAccess(null)) {
            constructor.setAccessible(true);
        }
        CSVRecord record = constructor.newInstance(values, mapping, comment, recordNumber);

        assertNull(record.getComment());
    }
}